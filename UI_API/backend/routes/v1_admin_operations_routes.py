"""Versioned Admin operations/configuration compatibility seam.

These handlers deliberately call the Operations capability interface directly;
the old ``/api`` endpoints remain only as a measured compatibility window.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

import config
from capabilities.identity_access import scope_from_admin_principal
from capabilities.operations_configuration import interface as operations
from utils.auth_utils import authorize_admin_request, check_rate_limit


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["v1-operations"])

    @router.get("/operations/build")
    async def get_build_metadata(request: Request):
        """Which build is running.

        The metadata itself needs no database, so it stays accurate when the
        schema state cannot be read. Authentication is a separate matter: with
        device security enforced, reaching this route still requires a session.
        """

        authorize_admin_request(request, "operations.read")
        return {"status": "success", "build": operations.build_metadata()}

    @router.delete("/operations/session-stats")
    async def clear_session_stats(request: Request):
        authorize_admin_request(request, "operations.write")
        await asyncio.to_thread(operations.clear_session_logs)
        return {"status": "success"}

    @router.get("/operations/session-stats")
    async def get_session_stats(request: Request):
        authorize_admin_request(request, "operations.read")
        logs = await asyncio.to_thread(operations.get_session_logs)
        stats = operations.compute_session_stats(logs)
        return {"status": "success", **stats}

    @router.get("/operations/logs")
    async def get_logs(request: Request):
        authorize_admin_request(request, "operations.read")
        logs = await asyncio.to_thread(operations.get_session_logs)
        indexed_logs = [{**dict(log), "_index": idx} for idx, log in enumerate(logs)]
        total = len(logs)
        success_count = sum(1 for log in logs if log.get("is_success", False))
        return {
            "total": total,
            "success_count": success_count,
            "success_rate": round((success_count / total * 100) if total > 0 else 0, 1),
            "logs": indexed_logs[-200:],
        }

    @router.delete("/operations/logs")
    async def clear_logs(request: Request):
        authorize_admin_request(request, "operations.write")
        await asyncio.to_thread(operations.clear_session_logs)
        return {"status": "success"}

    @router.delete("/operations/logs/{log_index}")
    async def delete_log(request: Request, log_index: int):
        authorize_admin_request(request, "operations.write")
        deleted = await asyncio.to_thread(operations.delete_session_log, log_index)
        return {"status": "success" if deleted else "not_found"}

    @router.get("/settings/llm-routing")
    async def llm_routing(request: Request):
        authorize_admin_request(request, "settings.read")
        return await asyncio.to_thread(operations.llm_readiness)

    @router.get("/settings/llm-traffic")
    async def llm_traffic(request: Request):
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

    @router.post("/settings/llm-connectivity-test")
    async def llm_connectivity_test(request: Request):
        authorize_admin_request(request, "settings.write")
        check_rate_limit(request, "admin_llm_connectivity_test", limit=10)
        return await asyncio.to_thread(operations.llm_connectivity_test)

    def _settings_changes(rows: list[dict], version: int) -> list[dict]:
        index = next((i for i, row in enumerate(rows) if row["version"] == version), -1)
        if index < 0:
            return []
        current = rows[index]["settings"]
        previous = rows[index + 1]["settings"] if index + 1 < len(rows) else {}
        return [
            {"key": key, "before": previous.get(key), "after": current.get(key)}
            for key in sorted(set(current) | set(previous))
            if current.get(key) != previous.get(key)
        ][:20]

    @router.get("/settings/versions")
    async def settings_versions(request: Request):
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

    @router.post("/settings/versions/{version}/rollback")
    async def rollback_settings_version(request: Request, version: int):
        principal = authorize_admin_request(request, "settings.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_settings_update", limit=30)
        target = await asyncio.to_thread(operations.get_settings_version, scope, version)
        if target is None:
            raise HTTPException(
                status_code=404, detail={"code": "settings_version_not_found", "message": "找不到這個設定版本。"}
            )
        saved_settings = operations.save_settings(target, scope, actor_id=principal.user_id)
        return {"status": "success", "restored_from": version, "settings": config.public_settings(saved_settings)}

    return router
