"""Versioned device session and credential transport."""

from fastapi import APIRouter

from routes import device_identity_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return device_identity_routes.create_router(deps, prefix="/api/v1")
