"""推薦事件路由。"""

import asyncio

from fastapi import APIRouter, Body, Request

from repositories import recommendation_event_repository
from services import recommendation_event_service
from services.commercial_context_service import scope_from_admin_principal, scope_from_device_principal
from utils.auth_utils import authorize_admin_request, check_rate_limit, require_kiosk_token


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["recommendation_events"])

    @router.post("/recommendation_events")
    async def post_recommendation_event(request: Request, payload: dict = Body(...)):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        session_id = str(payload.get("session_id") or "")
        check_rate_limit(request, "recommendation_events", limit=180, key=session_id)
        event = await asyncio.to_thread(
            recommendation_event_service.record_recommendation_event,
            payload,
            scope,
        )
        return {"status": "success", "event": event}

    @router.get("/recommendation_events")
    async def get_recommendation_events(request: Request, session_id: str = "", limit: int = 200):
        principal = authorize_admin_request(request, "recommendations.read")
        scope = scope_from_admin_principal(principal)
        events = await asyncio.to_thread(
            recommendation_event_repository.get_recommendation_events_scoped,
            scope,
            session_id,
            limit,
        )
        stats = recommendation_event_service.build_recommendation_event_stats(events)
        return {"status": "success", "events": events, **stats}

    @router.delete("/recommendation_events")
    async def clear_recommendation_events(request: Request):
        principal = authorize_admin_request(request, "recommendations.write")
        scope = scope_from_admin_principal(principal)
        count = await asyncio.to_thread(recommendation_event_repository.clear_recommendation_events_scoped, scope)
        return {"status": "success", "cleared": count}

    return router
