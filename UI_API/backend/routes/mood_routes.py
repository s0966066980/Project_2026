"""心情評分路由。"""
from fastapi import APIRouter, Body

from repositories import session_repository
from services.mood_service import MOOD_LABELS


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(tags=["mood"])

    @router.post("/api/session/mood")
    async def set_session_mood(payload: dict = Body(...)):
        """前端選完心情星星後呼叫，將 mood_score 寫入 session。"""
        session_id = str(payload.get("session_id") or "").strip()
        try:
            mood_score = int(payload.get("mood_score") or 0)
        except (ValueError, TypeError):
            mood_score = 0

        if not session_id or mood_score not in range(1, 6):
            return {"status": "error", "message": "invalid params"}

        mood_label = MOOD_LABELS.get(mood_score, "")
        session_repository.set_session_mood(session_id, mood_score, mood_label)
        return {"status": "ok", "mood_score": mood_score, "mood_label": mood_label}

    return router
