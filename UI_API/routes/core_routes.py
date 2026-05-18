import asyncio
import json

from fastapi import APIRouter, Body, Form
from fastapi.responses import FileResponse

import config
import database
from repositories import log_repository, session_repository


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(tags=["core"])

    @router.get("/")
    async def serve_frontend():
        return FileResponse("index.html")

    @router.get("/customer")
    async def serve_customer_service():
        return FileResponse("index.html")

    @router.get("/api/settings")
    async def get_settings():
        return config.load_settings()

    @router.post("/api/settings")
    async def update_settings(new_settings: dict = Body(...)):
        old_rag_settings = config.get("rag", {})
        config.save_settings(new_settings)
        if new_settings.get("rag") != old_rag_settings:
            deps["schedule_rag_rebuild"]("RAG settings changed")
        return {"status": "success"}

    @router.get("/api/logs")
    async def get_logs():
        logs = await asyncio.to_thread(log_repository.get_session_logs)
        indexed_logs = []
        for idx, log in enumerate(logs):
            row = dict(log)
            row["_index"] = idx
            indexed_logs.append(row)

        total = len(logs)
        success_count = sum(1 for log in logs if log.get("is_success", False))
        success_rate = round((success_count / total * 100) if total > 0 else 0, 1)
        ab_stats = {
            "A": {"impressions": 0, "successes": 0, "success_rate": 0},
            "B": {"impressions": 0, "successes": 0, "success_rate": 0},
        }
        for log in logs:
            variant_success = log.get("variant_success") or {}
            for variant in ("A", "B"):
                result = variant_success.get(variant) or {}
                if result.get("pushed_ids"):
                    ab_stats[variant]["impressions"] += 1
                    if result.get("is_success"):
                        ab_stats[variant]["successes"] += 1

        for variant in ("A", "B"):
            impressions = ab_stats[variant]["impressions"]
            successes = ab_stats[variant]["successes"]
            ab_stats[variant]["success_rate"] = round(
                (successes / impressions * 100) if impressions else 0, 1
            )

        return {
            "total": total,
            "success_count": success_count,
            "success_rate": success_rate,
            "logs": indexed_logs[-200:],
            "ab_stats": ab_stats,
        }

    @router.delete("/api/logs")
    async def clear_logs():
        await asyncio.to_thread(log_repository.clear_session_logs)
        deps["recommend_cache"].clear()
        return {"status": "success"}

    @router.delete("/api/logs/{log_index}")
    async def delete_log(log_index: int):
        deleted = await asyncio.to_thread(log_repository.delete_session_log, log_index)
        deps["recommend_cache"].clear()
        return {"status": "success" if deleted else "not_found"}

    @router.post("/api/checkout")
    async def process_checkout(
        session_id: str = Form(...),
        pushed_ids: str = Form(...),
        cart_ids: str = Form(...),
        pushed_variants: str = Form(default="{}"),
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
            pushed_variant_map = json.loads(pushed_variants) if pushed_variants else {}
        except (json.JSONDecodeError, ValueError):
            pushed_variant_map = {}

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
                    pushed_variant_map,
                ),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            log_entry = {"skipped": True}

        session_repository.archive_session(session_id)
        deps["emotion_cache"].pop(session_id, None)
        for key in list(deps["recommend_cache"].keys()):
            if key.startswith(f"{session_id}:"):
                deps["recommend_cache"].pop(key, None)
        return {"status": "success", "log": log_entry}

    return router
