"""Versioned Voice Evidence transport."""

from fastapi import APIRouter

from routes import voice_evidence_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return voice_evidence_routes.create_router(deps, prefix="/api/v1/voice-evidence")
