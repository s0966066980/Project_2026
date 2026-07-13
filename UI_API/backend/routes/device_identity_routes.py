"""Device credential exchange for short-lived browser sessions."""

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

import config
from services import device_identity_service
from utils.auth_utils import check_rate_limit


class DeviceSessionRequest(BaseModel):
    key_id: str = Field(min_length=1, max_length=128)
    credential: str = Field(min_length=16, max_length=1024)


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/device/auth", tags=["device-auth"])

    @router.post("/session")
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

    return router
