"""Versioned Voice Assistance transport.

The streaming implementation is shared with the compatibility route while
the canonical Kiosk client uses `/api/v1/ask/stream`.
"""

from fastapi import APIRouter

from routes import voice_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return voice_routes.create_router(deps, prefix="/api/v1")
