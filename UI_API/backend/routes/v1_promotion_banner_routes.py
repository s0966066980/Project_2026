"""Versioned customer-facing campaign banner transport."""

from fastapi import APIRouter

from routes import promotion_banner_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return promotion_banner_routes.create_router(deps, prefix="/api/v1")
