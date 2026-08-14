"""推薦事件路由。"""

import asyncio
import functools
from typing import Annotated

from fastapi import APIRouter, Body, Query, Request

from capabilities.identity_access import scope_from_admin_principal, scope_from_device_principal
from capabilities.operations_configuration import interface as operations
from capabilities.recommendation_analytics import recommendation_event_repository, recommendation_event_service
from utils.auth_utils import authorize_admin_request, check_rate_limit, require_kiosk_token


def create_router(deps: dict | None = None, *, prefix: str = "/api") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["recommendation_events"])

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
    async def clear_recommendation_events(
        request: Request,
        older_than_days: Annotated[
            int, Query(ge=0, le=3650)
        ] = recommendation_event_repository.DEFAULT_CLEAR_RETAIN_DAYS,
    ):
        """Clear this store's recommendation events older than a cutoff.

        The default keeps the last thirty days because the operations overview
        computes the push funnel from these rows; `older_than_days=0` clears
        everything, and has to be asked for.
        """

        principal = authorize_admin_request(request, "recommendations.write")
        scope = scope_from_admin_principal(principal)
        count = await asyncio.to_thread(
            functools.partial(
                recommendation_event_repository.clear_recommendation_events_scoped,
                scope,
                older_than_days=int(older_than_days),
            )
        )
        # Deleting operational history is an admin action, so it leaves one.
        await asyncio.to_thread(
            functools.partial(
                operations.record_admin_action,
                "recommendation_events_cleared",
                target_type="recommendation_events",
                target_id=str(scope.store_id),
                request=request,
                metadata={"older_than_days": int(older_than_days), "cleared": int(count)},
                scope=scope,
            )
        )
        return {"status": "success", "cleared": count, "older_than_days": int(older_than_days)}

    return router
