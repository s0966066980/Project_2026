import time

from fastapi import APIRouter, Form

import config
from repositories import menu_repository, session_repository
from services import recommendation_service


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["recommendation"])

    @router.post("/auto_recommend")
    async def process_auto_recommend(
        session_id: str = Form(...),
        force_default: str = Form(default="false"),
    ):
        try:
            force_default_mode = str(force_default).lower() in ("1", "true", "yes", "on")
            use_ai = bool(config.get("USE_AI_RECOMMEND", True)) and not force_default_mode

            # 預設推播：不呼叫 LLM。語音協助期間也走這條，避免同時佔用 Ollama。
            if not use_ai:
                menu_items = await __import__("asyncio").to_thread(menu_repository.get_menu)
                return recommendation_service.get_default_recommendation(menu_items)

            # AI 推播：Ollama
            history = session_repository.get_session_history(session_id)
            history_sig = recommendation_service.history_signature(history)
            cache_key = f"{session_id}:{history_sig}"
            now = time.time()
            cache_ttl = float(config.get("AUTO_RECOMMEND_MIN_GAP_SEC", 20))

            if config.get("ENABLE_RECOMMEND_CACHE", True):
                cached = deps["recommend_cache"].get(cache_key)
                if cached and now - cached["ts"] < cache_ttl:
                    cached_data = cached["data"].copy() if isinstance(cached.get("data"), dict) else {}
                    cached_data["cached"] = True
                    return cached_data

            response_data = await recommendation_service.generate_recommendation(
                session_id=session_id,
                emotion_cache=deps["emotion_cache"],
                ollama_semaphore=deps["ollama_semaphore"],
            )
            if response_data.get("status") == "success" and config.get("ENABLE_RECOMMEND_CACHE", True):
                recommendation_service.store_recommend_cache(
                    deps["recommend_cache"], cache_key, response_data, now
                )
            return response_data

        except Exception as e:
            print(f"❌ auto_recommend 錯誤: {e}")
            return {"status": "error", "message": str(e)}

    return router
