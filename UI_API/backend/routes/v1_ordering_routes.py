"""Versioned Ordering and Checkout transport.

The legacy routes remain registered during the measured compatibility window,
but both Kiosk and Admin clients use this capability-owned `/api/v1` surface.
The handlers are shared with the legacy transport so there is one ordering
implementation and one set of failure semantics.
"""

from fastapi import APIRouter

from routes import checkout_confirmation_routes, ordering_entry_routes


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter()
    router.include_router(ordering_entry_routes.create_router(deps, prefix="/api/v1/entry-flow"))
    router.include_router(checkout_confirmation_routes.create_router(deps, prefix="/api/v1"))
    return router
