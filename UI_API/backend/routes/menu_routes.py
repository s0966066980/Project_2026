"""Legacy `/api/menu*` transport.

These routes are compatibility adapters over the catalog capability and hold no
business rules of their own. Every request records which legacy operation was
used, so the decision to delete them rests on observed usage reaching zero
rather than on someone believing nothing calls them.
"""

import asyncio

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from capabilities import catalog
from capabilities.catalog import CatalogWriteError
from models.promotion_models import PosPromotionBannerResponse
from services import observability_service, promotion_banner_service
from services.commercial_context_service import scope_from_admin_principal, scope_from_device_principal
from utils.auth_utils import authorize_admin_request, require_kiosk_token
from utils.commercial_scope_config import resolve_commercial_scope

_LEGACY_STATUS = {
    "item_not_found": 404,
    "image_not_found": 404,
    "image_external": 404,
}


def _record_legacy_use(operation: str) -> None:
    observability_service.increment_metric(
        "legacy_catalog_requests_total",
        status=f"menu.{operation}",
    )


def _refused(exc: CatalogWriteError) -> HTTPException:
    return HTTPException(
        status_code=_LEGACY_STATUS.get(exc.code, 422),
        detail={"code": exc.code, "message": exc.message},
    )


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
        _record_legacy_use("get_menu")
        scope = _menu_scope_from_request(request)
        return await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)

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
        _record_legacy_use("list_items")
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
            catalog.list_items,
            scope,
            include_retired=include_retired,
            ensure_seed=True,
        )
        categories = sorted({str(item.get("category") or "") for item in items if item.get("category")})
        return {"status": "success", "items": items, "categories": categories}

    @router.post("/menu/items")
    async def create_menu_item(request: Request, payload: dict = Body(...)):
        _record_legacy_use("create_item")
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            item = await asyncio.to_thread(catalog.create_item, scope, payload)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return {"status": "success", "item": item}

    @router.put("/menu/items/{item_id}")
    async def update_menu_item(request: Request, item_id: str, payload: dict = Body(...)):
        _record_legacy_use("update_item")
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            item = await asyncio.to_thread(catalog.update_item, scope, item_id, payload)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return {"status": "success", "item": item}

    @router.post("/menu/items/{item_id}/retire")
    async def retire_menu_item(request: Request, item_id: str):
        _record_legacy_use("retire_item")
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            item = await asyncio.to_thread(catalog.retire_item, scope, item_id)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return {"status": "success", "item": item}

    @router.post("/menu/items/{item_id}/restore")
    async def restore_menu_item(request: Request, item_id: str):
        _record_legacy_use("restore_item")
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            item = await asyncio.to_thread(catalog.restore_item, scope, item_id)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return {"status": "success", "item": item}

    @router.post("/menu/items/{item_id}/image")
    async def upload_menu_item_image(request: Request, item_id: str, file: UploadFile = File(...)):
        _record_legacy_use("upload_image")
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        data = await file.read()
        try:
            item = await asyncio.to_thread(
                catalog.upload_item_image,
                scope,
                item_id,
                data=data,
                content_type=file.content_type or "",
                filename=file.filename or "upload.jpg",
            )
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return {"status": "success", "item": item}

    @router.get("/menu/items/{item_id}/image")
    async def get_menu_item_image(request: Request, item_id: str):
        _record_legacy_use("get_image")
        scope = _menu_scope_from_request(request)
        try:
            data, content_type = await asyncio.to_thread(catalog.load_item_image, scope, item_id)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return Response(content=data, media_type=content_type)

    @router.post("/menu")
    async def update_menu(request: Request, new_menu: list = Body(...)):
        """Bulk replace catalog for the admin store scope (writes scoped master, not raw JSON)."""

        _record_legacy_use("replace_catalog")
        principal = authorize_admin_request(request, "catalog.items.write")
        scope = scope_from_admin_principal(principal)
        try:
            items = await asyncio.to_thread(catalog.replace_catalog, scope, new_menu)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return {"status": "success", "count": len(items)}

    return router
