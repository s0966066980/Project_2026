"""Admin routes for store menu availability."""

import asyncio

from fastapi import APIRouter, Body, Request

from services import availability_service
from services.commercial_context_service import scope_from_admin_principal
from utils.auth_utils import authorize_admin_request


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
        scope = scope_from_admin_principal(principal)
        data = await asyncio.to_thread(availability_service.save_admin_state, payload, scope)
        return {"status": "success", **data}

    return router
