import asyncio

from fastapi import APIRouter, Body, Request

from repositories import interaction_event_repository
from services import interaction_event_service
from utils.auth_utils import require_admin_token


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/debug", tags=["debug"])

    @router.post("/interaction_risk")
    async def post_interaction_risk(request: Request, payload: dict = Body(...)):
        require_admin_token(request)
        session_id = str(payload.get("session_id") or "")
        ui_context = payload.get("ui_context") if isinstance(payload.get("ui_context"), dict) else {}
        events = await asyncio.to_thread(
            interaction_event_repository.get_recent_session_events,
            session_id,
        )
        risk_result = interaction_event_service.calculate_interaction_risk(events, ui_context)
        context = interaction_event_service.build_interaction_context(events, risk_result)
        return {
            "status": "success",
            "session_id": session_id,
            "risk_result": risk_result,
            "interaction_context": context,
        }

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
