"""AI 推播路由 — POST /api/ai_push"""
import json
from fastapi import APIRouter, Form
from services import ai_push_service


def _parse_ids(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(x) for x in data if x]
    except Exception:
        pass
    return [s.strip() for s in str(raw or "").split(",") if s.strip()]


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["ai_push"])

    @router.post("/ai_push")
    async def handle_ai_push(
        session_id: str = Form(...),
        exclude_ids: str = Form(default="[]"),
    ):
        return await ai_push_service.generate(
            session_id=session_id,
            ollama_semaphore=deps["ollama_semaphore"],
            exclude_ids=_parse_ids(exclude_ids),
        )

    @router.get("/assist_recommend")
    async def handle_assist_recommend(session_id: str):
        return await ai_push_service.generate_three(
            session_id=session_id,
            ollama_semaphore=deps["ollama_semaphore"],
        )

    return router
