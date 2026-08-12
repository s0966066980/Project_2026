"""Versioned recommendation event transport."""

from fastapi import APIRouter

from routes import recommendation_event_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return recommendation_event_routes.create_router(deps, prefix="/api/v1")
