"""Versioned Project Analyst status transport.

The sidecar and provider credentials remain an explicit deferred boundary; the
local UI API only exposes the same fail-closed status/analyse contract under v1.
"""

from fastapi import APIRouter

from routes import project_brain_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return project_brain_routes.create_router(deps, prefix="/api/v1/project-brain")
