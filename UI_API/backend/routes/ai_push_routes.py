"""AI 推播路由 — POST /api/ai_push"""
import json
from fastapi import APIRouter, Form, Request
from services import ai_push_service
from utils.auth_utils import check_rate_limit, require_kiosk_token


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
        request: Request,
        session_id: str = Form(...),
        exclude_ids: str = Form(default="[]"),
        cart_ids: str = Form(default="[]"),
    ):
        require_kiosk_token(request)
        check_rate_limit(request, "ai_push", limit=60, key=session_id)
        return await ai_push_service.generate(
            session_id=session_id,
            ollama_semaphore=deps["ollama_semaphore"],
            exclude_ids=_parse_ids(exclude_ids),
            cart_ids=_parse_ids(cart_ids),
        )

    @router.get("/assist_recommend")
    async def handle_assist_recommend(request: Request, session_id: str, cart_ids: str = "[]"):
        require_kiosk_token(request)
        check_rate_limit(request, "assist_recommend", limit=60, key=session_id)
        return await ai_push_service.generate_three(
            session_id=session_id,
            ollama_semaphore=deps["ollama_semaphore"],
            cart_ids=_parse_ids(cart_ids),
        )

    return router
