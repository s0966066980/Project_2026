"""Versioned recommendation assistance transport."""

from fastapi import APIRouter

from routes import ai_push_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return ai_push_routes.create_router(deps, prefix="/api/v1")
