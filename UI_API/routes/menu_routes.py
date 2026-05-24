import asyncio

from fastapi import APIRouter, Body, Request

import database
from repositories import menu_repository
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["menu"])

    @router.get("/menu")
    async def get_menu():
        return await asyncio.to_thread(menu_repository.get_menu)

    @router.post("/menu")
    async def update_menu(request: Request, new_menu: list = Body(...)):
        require_admin_token(request)
        if not isinstance(new_menu, list):
            return {"status": "error", "message": "menu payload must be a list"}

        # 菜單管理只負責保存菜單 JSON。RAG 內容改由手動新增或成功點餐事件建立，
        # 避免每次修改菜單都被 Ollama/RAG 審查阻塞，造成後台無法儲存。
        await asyncio.to_thread(database.update_menu, new_menu, False)
        deps["recommend_cache"].clear()
        schedule_rebuild = deps.get("schedule_rag_rebuild")
        if schedule_rebuild:
            schedule_rebuild("menu update")
        return {"status": "success", "count": len(new_menu)}

    return router
