import asyncio

from fastapi import APIRouter, Body, HTTPException, Request

import database
from models.promotion_models import PosPromotionBannerResponse
from repositories import menu_repository
from services import menu_validation_service, promotion_banner_service
from utils.auth_utils import authorize_admin_request


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["menu"])

    @router.get("/menu")
    async def get_menu():
        return await asyncio.to_thread(menu_repository.get_menu)

    @router.get("/promotions/pos-banner", response_model=PosPromotionBannerResponse)
    async def get_pos_promotion_banner(request: Request):
        surface = request.query_params.get("surface") or "pos_home_banner"
        return await asyncio.to_thread(promotion_banner_service.get_pos_banner_response, surface=surface)

    @router.post("/menu")
    async def update_menu(request: Request, new_menu: list = Body(...)):
        authorize_admin_request(request, "settings.write")
        try:
            validated_menu = menu_validation_service.validate_menu_payload(new_menu)
        except menu_validation_service.MenuValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"message": str(exc), "index": exc.index, "field": exc.field},
            ) from exc
        await asyncio.to_thread(database.update_menu, validated_menu)
        return {"status": "success", "count": len(validated_menu)}

    return router
