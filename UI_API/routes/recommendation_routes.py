import time

from fastapi import APIRouter, Form

import config
from repositories import session_repository
from services import recommendation_service


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["recommendation"])

    @router.post("/auto_recommend")
    async def process_auto_recommend(
        session_id: str = Form(...),
        ab_mode: str = Form(default="single"),
    ):
        try:
            history = session_repository.get_session_history(session_id)
            history_sig = recommendation_service.history_signature(history, ab_mode)
            current_emotion = deps["emotion_cache"].get(session_id)
            emotion_sig = recommendation_service.history_signature(
                [{"emotion": (current_emotion or {}).get("emotion_display") or (current_emotion or {}).get("emotion", "")}],
                "emotion",
            )
            cache_key = f"{session_id}:{ab_mode}:{history_sig}:{emotion_sig}"
            now = time.time()
            cache_ttl = float(config.get("AUTO_RECOMMEND_MIN_GAP_SEC", 20))
            if config.get("ENABLE_RECOMMEND_CACHE", True):
                cached = deps["recommend_cache"].get(cache_key)
                if cached and now - cached["ts"] < cache_ttl:
                    cached_data = cached["data"].copy()
                    cached_data["cached"] = True
                    return cached_data

            response_data = await recommendation_service.generate_recommendation(
                session_id=session_id,
                ab_mode=ab_mode,
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
