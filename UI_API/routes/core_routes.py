import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Form, Request
from fastapi.responses import FileResponse

import config
import database
from repositories import interaction_event_repository, log_repository, session_repository
from realtime import event_bus
from utils.auth_utils import require_admin_token


def _seconds_since_timestamp(timestamp: str) -> int:
    if not timestamp:
        return 0
    try:
        started_at = datetime.fromisoformat(str(timestamp))
        return max(0, int((datetime.now() - started_at).total_seconds()))
    except Exception:
        return 0


def _build_checkout_intervention_result(
    open_log: dict,
    checkout_success: bool,
    session_id: str,
    final_cart_ids: list | None = None,
) -> dict:
    result = dict(open_log.get("result") if isinstance(open_log.get("result"), dict) else {})
    barrier_result = open_log.get("barrier_result") if isinstance(open_log.get("barrier_result"), dict) else {}
    result.update({
        "session_id": session_id,
        "scenario_id": open_log.get("scenario_id") or barrier_result.get("scenario_id", ""),
        "scenario_label": open_log.get("scenario_label") or barrier_result.get("scenario_label", ""),
        "resolved": bool(checkout_success),
        "resolved_by": "checkout" if checkout_success else "",
        "checkout_success": bool(checkout_success),
        "payment_success": bool(checkout_success),
        "time_to_checkout_sec": _seconds_since_timestamp(open_log.get("timestamp", "")),
        "time_to_resolution_sec": _seconds_since_timestamp(open_log.get("timestamp", "")),
        "resolved_by_checkout": bool(checkout_success),
        "final_cart_ids": list(final_cart_ids or []),
    })
    if not checkout_success:
        result["resolved_by_checkout"] = False
    return result


def _mark_latest_intervention_checkout(
    session_id: str,
    checkout_success: bool = True,
    final_cart_ids: list | None = None,
) -> dict | None:
    open_log = interaction_event_repository.find_latest_open_intervention(session_id)
    if not open_log:
        return None
    intervention_id = str(open_log.get("intervention_id") or "")
    if not intervention_id:
        return None
    result = _build_checkout_intervention_result(
        open_log,
        checkout_success,
        session_id,
        final_cart_ids,
    )
    return interaction_event_repository.update_intervention_result(intervention_id, result)



def create_router(deps: dict) -> APIRouter:
    router = APIRouter(tags=["core"])

    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    @router.get("/")
    async def serve_frontend():
        return FileResponse("index.html", headers=_NO_CACHE)

    @router.get("/pos")
    async def serve_pos():
        return FileResponse("index.html", headers=_NO_CACHE)

    @router.get("/admin")
    async def serve_admin():
        return FileResponse("admin.html", headers=_NO_CACHE)

    @router.delete("/api/session_stats")
    async def clear_session_stats():
        await asyncio.to_thread(log_repository.clear_session_logs)
        return {"status": "success"}

    @router.get("/api/session_stats")
    async def get_session_stats():
        logs = await asyncio.to_thread(log_repository.get_session_logs)
        total = len(logs)
        total_clicks = sum(int(l.get("ai_push_cart_count", 0)) for l in logs)
        success_count = sum(1 for l in logs if l.get("ai_push_success", False))
        failure_count = total - success_count
        rate = round(success_count / total, 4) if total > 0 else 0.0
        sessions = [
            {
                "timestamp": l.get("timestamp", ""),
                "session_id": l.get("session_id", ""),
                "ai_push_cart_count": int(l.get("ai_push_cart_count", 0)),
                "ai_push_success": bool(l.get("ai_push_success", False)),
                "final_cart_ids": l.get("final_cart_ids", []),
            }
            for l in reversed(logs)
        ]
        return {
            "status": "success",
            "total_sessions": total,
            "total_ai_push_cart_clicks": total_clicks,
            "success_sessions": success_count,
            "failure_sessions": failure_count,
            "success_rate": rate,
            "cumulative_score": success_count - failure_count,
            "sessions": sessions,
        }


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
    ):
        try:
            pushed_list = json.loads(pushed_ids) if pushed_ids else []
        except (json.JSONDecodeError, ValueError):
            pushed_list = [x.strip() for x in pushed_ids.split(",") if x.strip()]
        try:
            cart_list = json.loads(cart_ids) if cart_ids else []
        except (json.JSONDecodeError, ValueError):
            cart_list = [x.strip() for x in cart_ids.split(",") if x.strip()]
        session_history = session_repository.get_session_history(session_id)
        try:
            loop = asyncio.get_running_loop()
            log_entry = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    database.record_final_checkout,
                    session_id,
                    pushed_list,
                    cart_list,
                    session_history,
                ),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            log_entry = {"skipped": True}

        intervention_result = await asyncio.to_thread(
            _mark_latest_intervention_checkout, session_id, True, cart_list
        )
        if intervention_result:
            log_entry = dict(log_entry or {})
            log_entry["recommendation_result"] = {
                "session_id": session_id,
                "pushed_ids": pushed_list,
                "final_cart_ids": cart_list,
                "is_success": bool(log_entry.get("is_success", False)),
            }
            log_entry["intervention_result"] = intervention_result

        try:
            ai_count = max(0, int(ai_push_cart_count or 0))
            logs = log_repository.get_session_logs()
            if logs:
                logs[-1]["ai_push_cart_count"] = ai_count
                logs[-1]["ai_push_success"] = ai_count >= 1
                log_repository.save_session_logs(logs)
            log_entry = dict(log_entry or {})
            log_entry["ai_push_cart_count"] = ai_count
            log_entry["ai_push_success"] = ai_count >= 1
        except Exception:
            log_entry = dict(log_entry or {})

        order_number = len(log_repository.get_session_logs())

        session_repository.archive_session(session_id)
        return {"status": "success", "log": log_entry, "order_number": order_number, "session_id": session_id}

    return router
