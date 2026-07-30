"""Device credential exchange for short-lived browser sessions."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

import config
from models.commercial_scope import CommercialScope
from services import device_identity_service
from utils.auth_utils import authorize_admin_request, check_rate_limit, require_kiosk_token
from utils.commercial_scope_config import resolve_commercial_scope


class DeviceSessionRequest(BaseModel):
    key_id: str = Field(min_length=1, max_length=128)
    credential: str = Field(min_length=16, max_length=1024)


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(tags=["device-auth"])

    @router.get("/api/device/auth/session")
    async def get_session(request: Request):
        """Return the database-owned device scope for the active browser session."""
        principal = require_kiosk_token(request)
        return {
            "authenticated": True,
            "device_id": str(principal.device_id),
            "store_id": str(principal.store_id),
            "tenant_id": str(principal.tenant_id),
            "expires_at": principal.expires_at.isoformat() if principal.expires_at else None,
            "auth_method": principal.auth_method,
        }

    @router.post("/api/device/auth/session")
    async def create_session(payload: DeviceSessionRequest, request: Request, response: Response):
        check_rate_limit(request, "device_auth", limit=10, key=payload.key_id)
        try:
            result = await asyncio.to_thread(
                device_identity_service.create_device_session,
                payload.key_id,
                payload.credential,
                untrusted_headers=request.headers,
            )
        except device_identity_service.DeviceAuthenticationError as exc:
            raise HTTPException(status_code=401, detail="Invalid device credential") from exc
        principal = result.principal
        cookie_name = str(config.get("DEVICE_SESSION_COOKIE_NAME", "kiosk_device_session"))
        response.set_cookie(
            key=cookie_name,
            value=result.token,
            expires=principal.expires_at,
            httponly=True,
            secure=config.is_production(),
            samesite="strict",
            path="/",
        )
        return {
            "device_id": str(principal.device_id),
            "store_id": str(principal.store_id),
            "tenant_id": str(principal.tenant_id),
            "expires_at": principal.expires_at.isoformat(),
        }

    @router.post("/api/admin/devices/{device_id}/credentials")
    async def issue_credential(device_id: UUID, request: Request):
        principal = authorize_admin_request(request, "device_identity.manage")
        configured = resolve_commercial_scope()
        scope = CommercialScope(principal.tenant_id, configured.store_id)
        issued = await asyncio.to_thread(
            device_identity_service.issue_device_credential,
            principal,
            scope,
            device_id,
        )
        return {
            "credential_id": str(issued.credential_id),
            "key_id": issued.key_id,
            "credential": issued.credential,
            "expires_at": issued.expires_at.isoformat(),
        }

    @router.post("/api/admin/device-credentials/{credential_id}/rotate")
    async def rotate_credential(credential_id: UUID, request: Request):
        principal = authorize_admin_request(request, "device_identity.manage")
        configured = resolve_commercial_scope()
        scope = CommercialScope(principal.tenant_id, configured.store_id)
        issued = await asyncio.to_thread(
            device_identity_service.rotate_device_credential,
            principal,
            scope,
            credential_id,
        )
        return {
            "credential_id": str(issued.credential_id),
            "key_id": issued.key_id,
            "credential": issued.credential,
            "expires_at": issued.expires_at.isoformat(),
        }

    @router.delete("/api/admin/device-credentials/{credential_id}")
    async def revoke_credential(credential_id: UUID, request: Request):
        principal = authorize_admin_request(request, "device_identity.manage")
        configured = resolve_commercial_scope()
        scope = CommercialScope(principal.tenant_id, configured.store_id)
        revoked = await asyncio.to_thread(
            device_identity_service.revoke_device_credential,
            principal,
            scope,
            credential_id,
        )
        if not revoked:
            raise HTTPException(status_code=404, detail="Device credential not found")
        return {"status": "revoked", "credential_id": str(credential_id)}

    return router
