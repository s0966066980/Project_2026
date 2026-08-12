"""Device-authenticated Admin identity transport."""

from fastapi import APIRouter, Request

from capabilities.identity_access import device_admin_principal


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

    @router.get("/me")
    async def current_admin(request: Request):
        principal = device_admin_principal(request)
        return {"principal": _principal_payload(principal), "access": "device_admin"}

    return router
