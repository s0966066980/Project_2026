import asyncio

from capabilities.identity_access import scope_from_admin_principal, scope_from_device_principal
from capabilities.operations_configuration import interface as operations
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError
from realtime import event_bus

import config
from core.constants import FRONTEND_DIR
from models.settings_contract import SettingsUpdateRequest
from utils.auth_utils import authorize_admin_request, check_rate_limit, require_kiosk_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(tags=["core"])

    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    @router.get("/")
    async def serve_frontend():
        return FileResponse(f"{FRONTEND_DIR}/kiosk/index.html", headers=_NO_CACHE)

    @router.get("/kiosk")
    async def serve_kiosk():
        return FileResponse(f"{FRONTEND_DIR}/kiosk/index.html", headers=_NO_CACHE)

    @router.get("/pos")
    async def serve_legacy_pos():
        return FileResponse(f"{FRONTEND_DIR}/kiosk/index.html", headers=_NO_CACHE)

    @router.get("/admin")
    async def serve_admin():
        return FileResponse(f"{FRONTEND_DIR}/admin/admin.html", headers=_NO_CACHE)

    @router.delete("/api/session_stats")
    async def clear_session_stats(request: Request):
        authorize_admin_request(request, "operations.write")
        await asyncio.to_thread(operations.clear_session_logs)
        return {"status": "success"}

    @router.get("/api/session_stats")
    async def get_session_stats(request: Request):
        authorize_admin_request(request, "operations.read")
        logs = await asyncio.to_thread(operations.get_session_logs)
        stats = operations.compute_session_stats(logs)
        return {"status": "success", **stats}

    @router.get("/api/public_settings")
    async def get_public_settings(request: Request):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        settings = operations.get_public_settings(scope)
        return {key: settings.get(key, config.DEFAULT_SETTINGS.get(key)) for key in config.PUBLIC_SETTINGS_KEYS}

    def _settings_changes(rows: list[dict], version: int) -> list[dict]:
        """Diff one version against the one before it, skipping unchanged keys."""
        index = next((i for i, row in enumerate(rows) if row["version"] == version), -1)
        if index < 0:
            return []
        current = rows[index]["settings"]
        previous = rows[index + 1]["settings"] if index + 1 < len(rows) else {}
        keys = sorted(set(current) | set(previous))
        return [
            {"key": key, "before": previous.get(key), "after": current.get(key)}
            for key in keys
            if current.get(key) != previous.get(key)
        ][:20]

    @router.get("/api/settings")
    async def get_settings(request: Request):
        principal = authorize_admin_request(request, "settings.read")
        scope = scope_from_admin_principal(principal)
        settings = operations.get_public_settings(scope)
        return config.with_effective_emotion_prompt(settings)

    @router.get("/api/settings/llm-routing")
    async def get_llm_routing(request: Request):
        """Whether each half of the configured chain can serve, without sending a prompt."""
        authorize_admin_request(request, "settings.read")
        return await asyncio.to_thread(operations.llm_readiness)

    @router.get("/api/settings/llm-traffic")
    async def get_llm_traffic(request: Request):
        """Which provider actually answered recently — the check against configured intent."""
        authorize_admin_request(request, "settings.read")
        counters = operations.llm_traffic_metrics()
        providers: dict[str, float] = {}
        fallbacks = 0.0
        for label, count in counters.items():
            provider, _, reason = str(label).partition("_")
            providers[provider] = providers.get(provider, 0.0) + float(count)
            if reason in {"timeout", "error", "schema_failure"}:
                fallbacks += float(count)
        return {
            "providers": {name: int(value) for name, value in sorted(providers.items())},
            "fallbacks": int(fallbacks),
            "total": int(sum(providers.values())),
        }

    @router.post("/api/settings/llm-connectivity-test")
    async def test_llm_connectivity(request: Request):
        """Send one real probe per configured provider. Changes no settings."""
        authorize_admin_request(request, "settings.write")
        check_rate_limit(request, "admin_llm_connectivity_test", limit=10)
        return await asyncio.to_thread(operations.llm_connectivity_test)

    @router.get("/api/settings/versions")
    async def list_settings_versions(request: Request):
        principal = authorize_admin_request(request, "settings.read")
        scope = scope_from_admin_principal(principal)
        rows = await asyncio.to_thread(operations.list_settings_versions, scope, 25)
        return {
            "versions": [
                {
                    "version": row["version"],
                    "actor_id": row["actor_id"],
                    "created_at": row["created_at"],
                    "changes": _settings_changes(rows, row["version"]),
                }
                for row in rows
            ]
        }

    @router.post("/api/settings/versions/{version}/rollback")
    async def rollback_settings_version(request: Request, version: int):
        principal = authorize_admin_request(request, "settings.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_settings_update", limit=30)
        target = await asyncio.to_thread(operations.get_settings_version, scope, version)
        if target is None:
            raise HTTPException(
                status_code=404, detail={"code": "settings_version_not_found", "message": "找不到這個設定版本。"}
            )
        # Roll forward to a copy of the old document rather than deleting versions, so the
        # rollback itself stays auditable.
        saved_settings = operations.save_settings(target, scope, actor_id=principal.user_id)
        await event_bus.publish_event(
            {
                "type": "settings_changed",
                "session_id": "",
                "payload": {"settings": config.public_settings(saved_settings)},
            }
        )
        return {"status": "success", "restored_from": version}

    @router.get("/api/admin/health")
    async def get_admin_health(request: Request):
        principal = authorize_admin_request(request, "operations.read")
        scope = scope_from_admin_principal(principal)
        actions = await asyncio.to_thread(operations.list_admin_audits, 500, scope)
        return await operations.build_admin_health(actions)

    async def record_health_incident_action(request: Request, incident_id: str, action: str, body: dict) -> dict:
        principal = authorize_admin_request(request, "operations.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_health_incident_action", limit=30)
        actions = await asyncio.to_thread(operations.list_admin_audits, 500, scope)
        current = await operations.build_admin_health(actions)
        incidents = current.get("operational", {}).get("incidents", [])
        incident = next((row for row in incidents if row.get("incident_id") == incident_id), None)
        if incident is None:
            raise HTTPException(status_code=404, detail="health incident is no longer active")
        reason = str((body or {}).get("reason") or "").strip()[:500]
        await asyncio.to_thread(
            operations.record_admin_action,
            action,
            target_type="health_incident",
            target_id=incident_id,
            request=request,
            metadata={"reason": reason, "check_key": incident.get("check_key", "")},
            scope=scope,
        )
        updated_actions = await asyncio.to_thread(operations.list_admin_audits, 500, scope)
        return await operations.build_admin_health(updated_actions)

    @router.post("/api/admin/health/incidents/{incident_id}/acknowledge")
    async def acknowledge_health_incident(request: Request, incident_id: str, body: dict = Body(default={})):
        return await record_health_incident_action(request, incident_id, "health.incident.acknowledge", body)

    @router.post("/api/admin/health/incidents/{incident_id}/escalate")
    async def escalate_health_incident(request: Request, incident_id: str, body: dict = Body(default={})):
        return await record_health_incident_action(request, incident_id, "health.incident.escalate", body)

    @router.post("/api/settings")
    async def update_settings(request: Request, new_settings: dict = Body(...)):
        principal = authorize_admin_request(request, "settings.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_settings_update", limit=30)
        submitted = new_settings if isinstance(new_settings, dict) else {}
        credentials = sorted(config.CREDENTIAL_SETTING_KEYS & set(submitted))
        if credentials:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "credential_not_accepted",
                    "message": f"{'、'.join(credentials)} 屬於憑證，請在 .env 設定後重啟服務。",
                },
            )
        try:
            validated = SettingsUpdateRequest.model_validate(submitted)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "settings_invalid",
                    "message": "設定內容有誤，請修正後再儲存。",
                    "field_errors": [
                        {
                            "path": ".".join(str(part) for part in error.get("loc") or ()),
                            "code": str(error.get("type") or "invalid"),
                            "message": str(error.get("msg") or "此欄位無效。"),
                        }
                        for error in exc.errors()
                    ],
                },
            ) from exc
        saved_settings = operations.save_settings(validated.changed_settings(), scope, actor_id=principal.user_id)
        await event_bus.publish_event(
            {
                "type": "settings_changed",
                "session_id": "",
                # broadcast_all reaches every connected client including kiosk devices, so only
                # the public projection may travel here — never the full settings document.
                "payload": {"settings": config.public_settings(saved_settings)},
            }
        )
        return {"status": "success"}

    @router.get("/api/logs")
    async def get_logs(request: Request):
        authorize_admin_request(request, "operations.read")
        logs = await asyncio.to_thread(operations.get_session_logs)
        indexed_logs = []
        for idx, log in enumerate(logs):
            row = dict(log)
            row["_index"] = idx
            indexed_logs.append(row)

        total = len(logs)
        success_count = sum(1 for log in logs if log.get("is_success", False))
        success_rate = round((success_count / total * 100) if total > 0 else 0, 1)
        return {
            "total": total,
            "success_count": success_count,
            "success_rate": success_rate,
            "logs": indexed_logs[-200:],
        }

    @router.delete("/api/logs")
    async def clear_logs(request: Request):
        authorize_admin_request(request, "operations.write")
        await asyncio.to_thread(operations.clear_session_logs)
        return {"status": "success"}

    @router.delete("/api/logs/{log_index}")
    async def delete_log(request: Request, log_index: int):
        authorize_admin_request(request, "operations.write")
        deleted = await asyncio.to_thread(operations.delete_session_log, log_index)
        return {"status": "success" if deleted else "not_found"}

    return router
