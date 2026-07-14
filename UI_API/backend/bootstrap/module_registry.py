"""Module registration for API routers and worker handlers."""

from __future__ import annotations

from typing import Iterable

from fastapi import APIRouter


def collect_v1_routers() -> list[APIRouter]:
    """Return module routers for /api/v1 composition.

    Modules are included when their api.py exists and exposes `router`.
    """

    routers: list[APIRouter] = []
    # Import lazily so missing modules during cutover do not break startup.
    candidates = (
        "modules.identity.api",
        "modules.device.api",
        "modules.catalog.api",
        "modules.member.api",
        "modules.ordering.api",
        "modules.promotion.api",
        "modules.recommendation.api",
        "modules.rag.api",
        "modules.intervention.api",
        "modules.fleet.api",
        "modules.analytics.api",
    )
    for dotted in candidates:
        try:
            module = __import__(dotted, fromlist=["router"])
        except ImportError:
            continue
        router = getattr(module, "router", None)
        if router is not None:
            routers.append(router)
    return routers


def include_module_routers(parent: APIRouter) -> APIRouter:
    for router in collect_v1_routers():
        parent.include_router(router)
    return parent
