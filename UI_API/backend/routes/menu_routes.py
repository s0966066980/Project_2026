import asyncio

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from models.promotion_models import PosPromotionBannerResponse
from repositories import menu_repository
from services import menu_catalog_service, promotion_banner_service
from services.commercial_context_service import scope_from_admin_principal, scope_from_device_principal
from utils.auth_utils import authorize_admin_request, require_kiosk_token
from utils.commercial_scope_config import resolve_commercial_scope


def _menu_scope_from_request(request: Request):
    """Prefer authenticated kiosk device scope; fall back to server default store."""

    try:
        principal = require_kiosk_token(request)
        return scope_from_device_principal(principal)
    except HTTPException:
        return resolve_commercial_scope()


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["menu"])

    @router.get("/menu")
    async def get_menu(request: Request):
        scope = _menu_scope_from_request(request)
        return await asyncio.to_thread(
            menu_repository.get_menu_scoped,
            scope,
            include_retired=False,
            ensure_seed=True,
        )

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

    @router.get("/menu/items")
    async def list_menu_items_admin(request: Request):
        # Managers use catalog.items.read; staff only has availability.read — both may list.
        try:
            principal = authorize_admin_request(request, "catalog.items.read")
        except HTTPException:
            principal = authorize_admin_request(request, "catalog.availability.read")
        scope = scope_from_admin_principal(principal)
        include_retired = str(request.query_params.get("include_retired") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        # Staff cannot list retired items.
        if include_retired:
            authorize_admin_request(request, "catalog.items.read")
        items = await asyncio.to_thread(
            menu_catalog_service.list_catalog,
            scope,
            include_retired=include_retired,
            ensure_seed=True,
        )
        categories = sorted({str(item.get("category") or "") for item in items if item.get("category")})
        return {"status": "success", "items": items, "categories": categories}

    @router.post("/menu/items")
    async def create_menu_item(request: Request, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            item = await asyncio.to_thread(menu_catalog_service.create_item, scope, payload)
        except menu_catalog_service.MenuCatalogError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
        return {"status": "success", "item": item}

    @router.put("/menu/items/{item_id}")
    async def update_menu_item(request: Request, item_id: str, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            item = await asyncio.to_thread(menu_catalog_service.update_item, scope, item_id, payload)
        except menu_catalog_service.MenuCatalogError as exc:
            status = 404 if exc.code == "item_not_found" else 422
            raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
        return {"status": "success", "item": item}

    @router.post("/menu/items/{item_id}/retire")
    async def retire_menu_item(request: Request, item_id: str):
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            item = await asyncio.to_thread(menu_catalog_service.retire_item, scope, item_id)
        except menu_catalog_service.MenuCatalogError as exc:
            status = 404 if exc.code == "item_not_found" else 422
            raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
        return {"status": "success", "item": item}

    @router.post("/menu/items/{item_id}/restore")
    async def restore_menu_item(request: Request, item_id: str):
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            item = await asyncio.to_thread(menu_catalog_service.restore_item, scope, item_id)
        except menu_catalog_service.MenuCatalogError as exc:
            status = 404 if exc.code == "item_not_found" else 422
            raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
        return {"status": "success", "item": item}

    @router.post("/menu/items/{item_id}/image")
    async def upload_menu_item_image(request: Request, item_id: str, file: UploadFile = File(...)):
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        data = await file.read()
        try:
            item = await asyncio.to_thread(
                menu_catalog_service.upload_item_image,
                scope,
                item_id,
                data=data,
                content_type=file.content_type or "",
                filename=file.filename or "upload.jpg",
            )
        except menu_catalog_service.MenuCatalogError as exc:
            status = 404 if exc.code == "item_not_found" else 422
            raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
        return {"status": "success", "item": item}

    @router.get("/menu/items/{item_id}/image")
    async def get_menu_item_image(request: Request, item_id: str):
        scope = _menu_scope_from_request(request)
        try:
            data, content_type = await asyncio.to_thread(
                menu_catalog_service.load_item_image_bytes,
                scope,
                item_id,
            )
        except menu_catalog_service.MenuCatalogError as exc:
            if exc.code == "image_external":
                raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message}) from exc
            status = 404 if exc.code in {"item_not_found", "image_not_found"} else 422
            raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
        return Response(content=data, media_type=content_type)

    @router.post("/menu")
    async def update_menu(request: Request, new_menu: list = Body(...)):
        """Bulk replace catalog for the admin store scope (writes scoped master, not raw JSON)."""

        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            items = await asyncio.to_thread(menu_catalog_service.replace_catalog, scope, new_menu)
        except menu_catalog_service.MenuCatalogError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
        return {"status": "success", "count": len(items)}

    return router
