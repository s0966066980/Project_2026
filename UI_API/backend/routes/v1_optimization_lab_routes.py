"""Versioned Optimization Lab transport."""

from fastapi import APIRouter

from routes import optimization_lab_routes


def create_router(deps: dict | None = None) -> APIRouter:
    return optimization_lab_routes.create_router(deps, prefix="/api/v1/optimization")
