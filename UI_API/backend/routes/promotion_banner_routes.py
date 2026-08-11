"""Customer-facing promotion banner transport.

This route belongs to Campaign & Promotion.  It used to share the legacy
catalog router only because that file predated the capability boundaries.
"""

import asyncio

from fastapi import APIRouter, Request

from models.promotion_models import PosPromotionBannerResponse
from services import promotion_banner_service
from services.commercial_context_service import scope_from_device_principal
from utils.auth_utils import require_kiosk_token


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["promotions"])

    @router.get("/promotions/pos-banner", response_model=PosPromotionBannerResponse)
    async def get_pos_promotion_banner(request: Request):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        surface = request.query_params.get("surface") or "pos_home_banner"
        return await asyncio.to_thread(
            promotion_banner_service.get_pos_banner_response,
            surface=surface,
            scope=scope,
        )

    return router
