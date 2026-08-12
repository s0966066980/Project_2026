"""Versioned operator push-copy authoring transport."""

from fastapi import APIRouter

from routes import push_copy_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return push_copy_routes.create_router(deps, prefix="/api/v1/push-copy")
