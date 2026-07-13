"""Minimal Admin login, logout, and current-session transport."""

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

import config
from services import admin_identity_service
from utils.auth_utils import require_admin_token
from utils.commercial_scope_config import resolve_commercial_scope


class AdminLoginRequest(BaseModel):
    login_identity: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


def _principal_payload(principal) -> dict:
    return {
        "user_id": str(principal.user_id),
        "tenant_id": str(principal.tenant_id),
        "allowed_store_ids": [str(value) for value in principal.allowed_store_ids],
        "roles": list(principal.roles),
        "permissions": list(principal.permissions),
        "session_id": str(principal.session_id) if principal.session_id else None,
        "auth_method": principal.auth_method,
    }


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])

    @router.post("/login")
    async def login(payload: AdminLoginRequest, request: Request, response: Response):
        scope = resolve_commercial_scope(request.headers)
        try:
            result = await asyncio.to_thread(
                admin_identity_service.login_admin,
                payload.login_identity,
                payload.password,
                scope,
            )
        except admin_identity_service.AdminAuthenticationError as exc:
            raise HTTPException(status_code=401, detail="Invalid credentials") from exc
        response.set_cookie(
            key=str(config.get("ADMIN_SESSION_COOKIE_NAME", "admin_session")),
            value=result.token,
            expires=result.expires_at,
            httponly=True,
            secure=config.is_production(),
            samesite="strict",
            path="/",
        )
        return {"principal": _principal_payload(result.principal), "expires_at": result.expires_at.isoformat()}

    @router.post("/logout")
    async def logout(request: Request, response: Response):
        principal = require_admin_token(request)
        cookie_name = str(config.get("ADMIN_SESSION_COOKIE_NAME", "admin_session"))
        token = request.cookies.get(cookie_name, "")
        if principal and principal.auth_method == "session":
            await asyncio.to_thread(admin_identity_service.logout_admin, token, resolve_commercial_scope())
        response.delete_cookie(cookie_name, path="/", httponly=True, samesite="strict")
        return {"status": "success"}

    @router.get("/me")
    async def current_admin(request: Request):
        return {"principal": _principal_payload(require_admin_token(request))}

    return router
