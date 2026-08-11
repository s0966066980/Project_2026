"""Legacy `/api/availability` transport.

A compatibility adapter over the catalog capability with no rules of its own.
Usage is recorded so deletion can rest on observed traffic rather than belief.
"""

import asyncio

from fastapi import APIRouter, Body, Request

from capabilities import catalog
from services import admin_audit_service, observability_service
from services.commercial_context_service import scope_from_admin_principal
from utils.auth_utils import authorize_admin_request, check_rate_limit


def _record_legacy_use(operation: str) -> None:
    observability_service.increment_metric(
        "legacy_catalog_requests_total",
        status=f"availability.{operation}",
    )


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["availability"])

    @router.get("/availability")
    async def get_availability(request: Request):
        principal = authorize_admin_request(request, "catalog.availability.read")
        scope = scope_from_admin_principal(principal)
        _record_legacy_use("get_availability")
        data = await asyncio.to_thread(catalog.get_availability, scope)
        return {"status": "success", **data}

    @router.post("/availability")
    async def save_availability(request: Request, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "catalog.availability.write")
        check_rate_limit(request, "staff_availability_update", limit=60)
        scope = scope_from_admin_principal(principal)
        _record_legacy_use("save_availability")
        data = await asyncio.to_thread(catalog.save_availability, scope, payload)
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
