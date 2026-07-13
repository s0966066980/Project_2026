import asyncio

from fastapi import APIRouter, Body, Form, HTTPException, Request
from fastapi.responses import FileResponse
from realtime import event_bus

import config
from core.constants import FRONTEND_DIR
from repositories import commercial_settings_repository, log_repository
from services import (
    checkout_pricing_service,
    checkout_service,
    health_service,
    member_service,
    observability_service,
    stats_service,
)
from services.commercial_context_service import scope_from_admin_principal, scope_from_device_principal
from utils.auth_utils import authorize_admin_request, check_rate_limit, require_kiosk_token
from utils.parsing import parse_json_list, parse_non_negative_int


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
        await asyncio.to_thread(log_repository.clear_session_logs)
        return {"status": "success"}

    @router.get("/api/session_stats")
    async def get_session_stats(request: Request):
        authorize_admin_request(request, "operations.read")
        logs = await asyncio.to_thread(log_repository.get_session_logs)
        return {"status": "success", **stats_service.compute_session_stats(logs)}

    @router.get("/api/public_settings")
    async def get_public_settings(request: Request):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        settings = commercial_settings_repository.get_settings_scoped(scope)
        return {
            key: settings.get(key, config.DEFAULT_SETTINGS.get(key))
            for key in config.PUBLIC_SETTINGS_KEYS
        }

    @router.get("/api/settings")
    async def get_settings(request: Request):
        principal = authorize_admin_request(request, "settings.read")
        scope = scope_from_admin_principal(principal)
        return commercial_settings_repository.get_settings_scoped(scope)

    @router.get("/api/admin/health")
    async def get_admin_health(request: Request):
        authorize_admin_request(request, "operations.read")
        return await health_service.build_admin_health()

    @router.post("/api/settings")
    async def update_settings(request: Request, new_settings: dict = Body(...)):
        principal = authorize_admin_request(request, "settings.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_settings_update", limit=30)
        saved_settings = commercial_settings_repository.save_settings_scoped(
            new_settings, scope, actor_id=principal.user_id
        )
        await event_bus.publish_event(
            {
                "type": "settings_changed",
                "session_id": "",
                "payload": {"settings": saved_settings},
            }
        )
        return {"status": "success"}

    @router.get("/api/logs")
    async def get_logs(request: Request):
        authorize_admin_request(request, "operations.read")
        logs = await asyncio.to_thread(log_repository.get_session_logs)
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
        await asyncio.to_thread(log_repository.clear_session_logs)
        return {"status": "success"}

    @router.delete("/api/logs/{log_index}")
    async def delete_log(request: Request, log_index: int):
        authorize_admin_request(request, "operations.write")
        deleted = await asyncio.to_thread(log_repository.delete_session_log, log_index)
        return {"status": "success" if deleted else "not_found"}

    @router.post("/api/checkout")
    async def process_checkout(
        request: Request,
        session_id: str = Form(...),
        pushed_ids: str = Form(...),
        cart_ids: str = Form(...),
        cart_items: str = Form(default="[]"),
        ai_push_cart_count: str = Form(default="0"),
        cart_sources: str = Form(default="[]"),
        cart_total: str = Form(default="0"),
    ):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal) if principal is not None else None
        check_rate_limit(request, "checkout", limit=120, key=session_id)
        parsed_cart_ids = parse_json_list(cart_ids, fallback_csv=True)
        parsed_cart_items = parse_json_list(cart_items)
        member = await asyncio.to_thread(
            member_service.get_session_member,
            session_id,
            *(() if scope is None else (scope,)),
        )
        try:
            priced_cart = await asyncio.to_thread(
                checkout_pricing_service.price_checkout_cart,
                parsed_cart_items,
                parsed_cart_ids,
                is_member=bool(member),
                scope=scope,
            )
        except checkout_pricing_service.CartValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        checkout_args = (
            session_id,
            parse_json_list(pushed_ids, fallback_csv=True),
            priced_cart["cart_ids"],
            priced_cart["cart_items"],
            parse_non_negative_int(ai_push_cart_count),
            parse_json_list(cart_sources),
            priced_cart["total"],
            scope,
            str(request.headers.get("Idempotency-Key") or f"legacy:{session_id}"),
            priced_cart,
        )
        correlation_token = (
            observability_service.bind_correlation_context(
                tenant_id=scope.tenant_id,
                store_id=scope.store_id,
                device_id=scope.device_id,
            )
            if scope is not None
            else None
        )
        request.state.commercial_scope = scope
        try:
            result = await checkout_service.process_checkout(*checkout_args)
        except checkout_service.CheckoutIdempotencyConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "idempotency_conflict", "message": str(exc)},
            ) from exc
        finally:
            if correlation_token is not None:
                observability_service.reset_correlation_context(correlation_token)
        result["cart_total"] = priced_cart["total"]
        return result

    return router
