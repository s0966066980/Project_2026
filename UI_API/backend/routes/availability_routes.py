"""Admin routes for store menu availability."""

import asyncio

from fastapi import APIRouter, Body, Request

from services import admin_audit_service, availability_service
from services.commercial_context_service import scope_from_admin_principal
from utils.auth_utils import authorize_admin_request, check_rate_limit


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["availability"])

    @router.get("/availability")
    async def get_availability(request: Request):
        principal = authorize_admin_request(request, "catalog.availability.read")
        scope = scope_from_admin_principal(principal)
        data = await asyncio.to_thread(availability_service.get_admin_state, None, scope)
        return {"status": "success", **data}

    @router.post("/availability")
    async def save_availability(request: Request, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "catalog.availability.write")
        check_rate_limit(request, "staff_availability_update", limit=60)
        scope = scope_from_admin_principal(principal)
        data = await asyncio.to_thread(availability_service.save_admin_state, payload, scope)
        await asyncio.to_thread(
            admin_audit_service.record_admin_action,
            "admin_availability.update",
            target_type="availability",
            target_id=str(scope.store_id),
            request=request,
            metadata={"actor_type": "manager"},
            scope=scope,
        )
        return {"status": "success", **data}

    return router
