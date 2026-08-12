"""Versioned local diagnostics transport.

The implementation remains the local Ollama diagnostic service; this module only
publishes the canonical HTTP seam used by Admin. External provider credentials
are intentionally not introduced here.
"""

from fastapi import APIRouter

from routes import diagnostic_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return diagnostic_routes.create_router(deps, prefix="/api/v1/diagnostics")
