import asyncio
import json

from fastapi import APIRouter, Body, Form, Request
from fastapi.responses import FileResponse

import config
from repositories import log_repository
from realtime import event_bus
from services import checkout_service, stats_service
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(tags=["core"])

    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    @router.get("/")
    async def serve_frontend():
        return FileResponse("frontend/pos/index.html", headers=_NO_CACHE)

    @router.get("/pos")
    async def serve_pos():
        return FileResponse("frontend/pos/index.html", headers=_NO_CACHE)

    @router.get("/admin")
    async def serve_admin():
        return FileResponse("frontend/admin/admin.html", headers=_NO_CACHE)

    @router.delete("/api/session_stats")
    async def clear_session_stats():
        await asyncio.to_thread(log_repository.clear_session_logs)
        return {"status": "success"}

    @router.get("/api/session_stats")
    async def get_session_stats():
        logs = await asyncio.to_thread(log_repository.get_session_logs)
        return {"status": "success", **stats_service.compute_session_stats(logs)}


    @router.get("/api/public_settings")
    async def get_public_settings():
        return config.load_public_settings()

    @router.get("/api/settings")
    async def get_settings(request: Request):
        require_admin_token(request)
        return config.load_settings()

    @router.post("/api/settings")
    async def update_settings(request: Request, new_settings: dict = Body(...)):
        require_admin_token(request)
        config.save_settings(new_settings)
        saved_settings = config.load_settings()
        await event_bus.publish_event({
            "type": "settings_changed",
            "session_id": "",
            "payload": {"settings": saved_settings},
        })
        return {"status": "success"}

    @router.get("/api/logs")
    async def get_logs(request: Request):
        require_admin_token(request)
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
        require_admin_token(request)
        await asyncio.to_thread(log_repository.clear_session_logs)
        return {"status": "success"}

    @router.delete("/api/logs/{log_index}")
    async def delete_log(request: Request, log_index: int):
        require_admin_token(request)
        deleted = await asyncio.to_thread(log_repository.delete_session_log, log_index)
        return {"status": "success" if deleted else "not_found"}

    @router.post("/api/checkout")
    async def process_checkout(
        session_id: str = Form(...),
        pushed_ids: str = Form(...),
        cart_ids: str = Form(...),
        ai_push_cart_count: str = Form(default="0"),
        cart_sources: str = Form(default="[]"),
    ):
        try:
            pushed_list = json.loads(pushed_ids) if pushed_ids else []
        except (json.JSONDecodeError, ValueError):
            pushed_list = [x.strip() for x in pushed_ids.split(",") if x.strip()]
        try:
            cart_list = json.loads(cart_ids) if cart_ids else []
        except (json.JSONDecodeError, ValueError):
            cart_list = [x.strip() for x in cart_ids.split(",") if x.strip()]
        try:
            sources = json.loads(cart_sources) if cart_sources else []
            if not isinstance(sources, list):
                sources = []
        except (json.JSONDecodeError, ValueError):
            sources = []
        ai_count = max(0, int(ai_push_cart_count or 0))

        return await checkout_service.process_checkout(
            session_id, pushed_list, cart_list, ai_count, sources
        )

    return router
