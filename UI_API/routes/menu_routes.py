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
        await asyncio.to_thread(database.update_menu, new_menu)
        return {"status": "success", "count": len(new_menu)}

    return router
