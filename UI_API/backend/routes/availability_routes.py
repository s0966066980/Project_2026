"""Admin routes for store menu availability."""
import asyncio

from fastapi import APIRouter, Body, Request

from services import availability_service
from utils.auth_utils import require_admin_token


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["availability"])

    @router.get("/availability")
    async def get_availability(request: Request):
        require_admin_token(request)
        data = await asyncio.to_thread(availability_service.get_admin_state)
        return {"status": "success", **data}

    @router.post("/availability")
    async def save_availability(request: Request, payload: dict = Body(...)):
        require_admin_token(request)
        data = await asyncio.to_thread(availability_service.save_admin_state, payload)
        return {"status": "success", **data}

    return router
