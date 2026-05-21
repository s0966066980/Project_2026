import asyncio

from fastapi import APIRouter, Body, Request

import database
from repositories import menu_repository
from services import rag_review_service
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["menu"])

    @router.get("/menu")
    async def get_menu():
        return await asyncio.to_thread(menu_repository.get_menu)

    @router.post("/menu")
    async def update_menu(request: Request, new_menu: list = Body(...)):
        require_admin_token(request)
        loop = asyncio.get_running_loop()
        active_ids = {str(item.get("id", "")) for item in new_menu if item.get("id")}
        await asyncio.to_thread(database.mark_missing_menu_rag_docs_deleted, active_ids)

        for item in new_menu:
            if not item.get("id"):
                continue
            source_text = database.build_menu_item_text(item)
            review_result = await rag_review_service.review_rag_text(
                source_text,
                "menu",
                str(item.get("id")),
                deps["ollama_semaphore"],
            )
            await asyncio.to_thread(
                database.upsert_reviewed_rag_doc,
                "menu", str(item.get("id")), source_text, review_result
            )

        await loop.run_in_executor(None, database.update_menu, new_menu)
        deps["recommend_cache"].clear()
        return {"status": "success"}

    return router
