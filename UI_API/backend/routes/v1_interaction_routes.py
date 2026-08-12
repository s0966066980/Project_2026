"""Versioned interaction telemetry transport."""

from fastapi import APIRouter

from routes import interaction_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return interaction_routes.create_router(deps, prefix="/api/v1")
