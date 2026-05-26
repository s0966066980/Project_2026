"""AI 推播路由：/api/auto_recommend 專利展示用，永遠走 Ollama，失敗時回預設熱門。"""
import asyncio

from fastapi import APIRouter, Form

from repositories import menu_repository
from services import recommendation_service


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["recommendation"])

    @router.post("/auto_recommend")
    async def process_auto_recommend(session_id: str = Form(...)):
        try:
            menu_items = await asyncio.to_thread(menu_repository.get_menu)
            response = await recommendation_service.generate_recommendation(
                session_id=session_id,
                ollama_semaphore=deps["ollama_semaphore"],
            )
            if response.get("status") != "success":
                fallback = recommendation_service.get_default_recommendation(menu_items)
                fallback["mode"] = "default_fallback"
                return fallback
            return response
        except Exception as e:
            print(f"❌ auto_recommend 錯誤: {e}")
            menu_items = await asyncio.to_thread(menu_repository.get_menu)
            return recommendation_service.get_default_recommendation(menu_items)

    return router
