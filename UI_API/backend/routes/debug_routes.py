import asyncio

from fastapi import APIRouter, Request

from repositories import interaction_event_repository
from utils.auth_utils import require_admin_token


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/debug", tags=["debug"])

    @router.get("/intervention_logs/{session_id}")
    async def get_intervention_logs(request: Request, session_id: str, limit: int = 200):
        require_admin_token(request)
        logs = await asyncio.to_thread(
            interaction_event_repository.get_intervention_logs,
            session_id,
            limit,
        )
        return {"status": "success", "session_id": session_id, "logs": logs}

    return router
