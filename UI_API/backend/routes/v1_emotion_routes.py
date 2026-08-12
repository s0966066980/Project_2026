"""Versioned Emotion Diagnostics transport."""

from fastapi import APIRouter

from routes import emotion_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return emotion_routes.create_router(deps, prefix="/api/v1/emotion")
