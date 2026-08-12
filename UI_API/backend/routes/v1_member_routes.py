"""Versioned Member and Kiosk membership transport."""

from fastapi import APIRouter

from routes import member_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return member_routes.create_router(deps, prefix="/api/v1")
