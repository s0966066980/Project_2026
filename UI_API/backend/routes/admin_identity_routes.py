"""Minimal Admin login, logout, and current-session transport."""

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

import config
from services import admin_identity_service
from utils.auth_utils import check_rate_limit, require_admin_token, staff_principal_from_device
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

    @router.get("/ui-config")
    async def ui_config():
        """Expose non-secret behavior required before the Admin login completes."""
        return {
            "manager_login_identity": config.ADMIN_MANAGER_LOGIN_IDENTITY,
            "manager_idle_timeout_sec": max(1, int(config.ADMIN_MANAGER_IDLE_TIMEOUT_SEC)),
        }

    @router.post("/login")
    async def login(payload: AdminLoginRequest, request: Request, response: Response):
        check_rate_limit(request, "admin_login", limit=10, key=payload.login_identity.strip().lower())
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
        cookie_name = str(config.get("ADMIN_SESSION_COOKIE_NAME", "admin_session"))
        token = request.cookies.get(cookie_name, "")
        principal = admin_identity_service.authenticate_admin_session(token) if token else None
        if principal is not None:
            await asyncio.to_thread(admin_identity_service.logout_admin, token, resolve_commercial_scope())
        response.delete_cookie(cookie_name, path="/", httponly=True, samesite="strict")
        return {"status": "success"}

    @router.get("/me")
    async def current_admin(request: Request):
        """回傳目前身分：有主管 session 就是主管，否則退回裝置憑證發放的員工身分。

        Admin 頁面預設以員工模式開啟（一般員工不需要登入），主管功能才需要密碼，
        因此這裡不能在沒有主管 session 時直接 401。
        """
        try:
            principal = require_admin_token(request)
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
            principal = staff_principal_from_device(request)
        return {"principal": _principal_payload(principal), "manager": principal.auth_method != "device_staff"}

    @router.post("/rotate")
    async def rotate(request: Request, response: Response):
        principal = require_admin_token(request)
        if principal.auth_method != "session":
            raise HTTPException(status_code=403, detail="legacy Admin authentication cannot rotate a session")
        cookie_name = str(config.get("ADMIN_SESSION_COOKIE_NAME", "admin_session"))
        result = await asyncio.to_thread(
            admin_identity_service.rotate_admin_session,
            request.cookies.get(cookie_name, ""),
            resolve_commercial_scope(),
        )
        response.set_cookie(
            key=cookie_name,
            value=result.token,
            expires=result.expires_at,
            httponly=True,
            secure=config.is_production(),
            samesite="strict",
            path="/",
        )
        return {"principal": _principal_payload(result.principal), "expires_at": result.expires_at.isoformat()}

    return router
