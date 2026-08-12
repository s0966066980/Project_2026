"""Capability-centered `/api/v1/catalog` transport.

The routes live in the legacy transport layer for now because a capability
package may not import `services` or `utils`, and admin scope resolution still
lives there. The contract is already capability-shaped, so moving the file
later does not move the API.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from api.v1.catalog_contracts import (
    CatalogAvailabilityCommandDTO,
    CatalogAvailabilityDTO,
    CatalogItemDTO,
    CatalogItemListDTO,
    CatalogItemWriteDTO,
    catalog_availability_dto,
    catalog_item_dto,
)
from api.v1.contracts import ApiErrorResponse, ApiMeta, ApiResponse
from capabilities import catalog
from capabilities.catalog import CatalogWriteError
from capabilities.identity_access import scope_from_admin_principal, scope_from_device_principal
from capabilities.operations_configuration import interface as operations
from models.commercial_scope import CommercialScope
from utils.auth_utils import authorize_admin_request, check_rate_limit, require_kiosk_token
from utils.commercial_scope_config import resolve_commercial_scope


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=str(request.state.request_id), timestamp=datetime.now(timezone.utc))


# A refusal names why. Mapping every one of them onto 422 would tell an
# operator that a five-megabyte upload and a missing item are the same problem.
_ERROR_STATUS = {
    "item_not_found": 404,
    "image_not_found": 404,
    "image_external": 404,
    "image_too_large": 413,
    "image_type_not_allowed": 415,
    "image_processing_unavailable": 503,
    "image_storage_failed": 503,
}


def _refused(exc: CatalogWriteError) -> HTTPException:
    return HTTPException(
        status_code=_ERROR_STATUS.get(exc.code, 422),
        detail={"code": exc.code, "message": exc.message},
    )


def _write_scope(request: Request) -> CommercialScope:
    return scope_from_admin_principal(authorize_admin_request(request, "catalog.items.write"))


def _read_scope(request: Request, *, include_retired: bool) -> CommercialScope:
    """Retired items are an operator view; the sellable catalog is not.

    A kiosk device may read what it can sell without an admin permission, but
    listing retired items is catalog management and is authorised as such.
    """

    if include_retired:
        return scope_from_admin_principal(authorize_admin_request(request, "catalog.items.read"))
    try:
        return scope_from_device_principal(require_kiosk_token(request))
    except HTTPException:
        return resolve_commercial_scope()


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/catalog",
        tags=["v1-catalog"],
        responses={
            401: {"model": ApiErrorResponse, "description": "Device or admin authentication required"},
            403: {"model": ApiErrorResponse, "description": "Permission denied"},
            404: {"model": ApiErrorResponse, "description": "Catalog item not found"},
        },
    )

    @router.get(
        "/items",
        operation_id="v1_list_catalog_items",
        response_model=ApiResponse[CatalogItemListDTO],
    )
    async def list_catalog_items(
        request: Request,
        include_retired: bool = Query(default=False),
    ) -> ApiResponse[CatalogItemListDTO]:
        scope = _read_scope(request, include_retired=include_retired)
        request.state.commercial_scope = scope
        rows = await asyncio.to_thread(
            catalog.list_items,
            scope,
            include_retired=include_retired,
            ensure_seed=True,
        )
        items = [catalog_item_dto(row) for row in rows]
        return ApiResponse(
            data=CatalogItemListDTO(
                items=items,
                categories=sorted({item.category for item in items if item.category}),
            ),
            meta=_meta(request),
        )

    @router.get(
        "/items/{item_id}",
        operation_id="v1_get_catalog_item",
        response_model=ApiResponse[CatalogItemDTO],
    )
    async def get_catalog_item(
        request: Request,
        item_id: str,
        include_retired: bool = Query(default=False),
    ) -> ApiResponse[CatalogItemDTO]:
        scope = _read_scope(request, include_retired=include_retired)
        request.state.commercial_scope = scope
        row = await asyncio.to_thread(catalog.get_item, scope, item_id, include_retired=include_retired)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "item_not_found", "message": "catalog item not found"})
        return ApiResponse(data=catalog_item_dto(row), meta=_meta(request))

    @router.post(
        "/items",
        status_code=201,
        operation_id="v1_create_catalog_item",
        response_model=ApiResponse[CatalogItemDTO],
    )
    async def create_catalog_item(request: Request, payload: CatalogItemWriteDTO) -> ApiResponse[CatalogItemDTO]:
        scope = _write_scope(request)
        request.state.commercial_scope = scope
        try:
            row = await asyncio.to_thread(catalog.create_item, scope, payload.model_dump(exclude_none=True))
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return ApiResponse(data=catalog_item_dto(row), meta=_meta(request))

    @router.patch(
        "/items/{item_id}",
        operation_id="v1_update_catalog_item",
        response_model=ApiResponse[CatalogItemDTO],
    )
    async def update_catalog_item(
        request: Request,
        item_id: str,
        payload: CatalogItemWriteDTO,
    ) -> ApiResponse[CatalogItemDTO]:
        scope = _write_scope(request)
        request.state.commercial_scope = scope
        try:
            row = await asyncio.to_thread(catalog.update_item, scope, item_id, payload.model_dump(exclude_none=True))
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return ApiResponse(data=catalog_item_dto(row), meta=_meta(request))

    @router.post(
        "/items/{item_id}/retirement",
        operation_id="v1_retire_catalog_item",
        response_model=ApiResponse[CatalogItemDTO],
    )
    async def retire_catalog_item(request: Request, item_id: str) -> ApiResponse[CatalogItemDTO]:
        scope = _write_scope(request)
        request.state.commercial_scope = scope
        try:
            row = await asyncio.to_thread(catalog.retire_item, scope, item_id)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return ApiResponse(data=catalog_item_dto(row), meta=_meta(request))

    @router.delete(
        "/items/{item_id}/retirement",
        operation_id="v1_restore_catalog_item",
        response_model=ApiResponse[CatalogItemDTO],
    )
    async def restore_catalog_item(request: Request, item_id: str) -> ApiResponse[CatalogItemDTO]:
        scope = _write_scope(request)
        request.state.commercial_scope = scope
        try:
            row = await asyncio.to_thread(catalog.restore_item, scope, item_id)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return ApiResponse(data=catalog_item_dto(row), meta=_meta(request))

    @router.put(
        "/items/{item_id}/image",
        operation_id="v1_upload_catalog_item_image",
        response_model=ApiResponse[CatalogItemDTO],
    )
    async def upload_catalog_item_image(
        request: Request,
        item_id: str,
        file: UploadFile = File(...),
    ) -> ApiResponse[CatalogItemDTO]:
        scope = _write_scope(request)
        request.state.commercial_scope = scope
        data = await file.read()
        try:
            row = await asyncio.to_thread(
                catalog.upload_item_image,
                scope,
                item_id,
                data=data,
                content_type=file.content_type or "",
                filename=file.filename or "upload.jpg",
            )
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return ApiResponse(data=catalog_item_dto(row), meta=_meta(request))

    @router.get(
        "/items/{item_id}/image",
        operation_id="v1_get_catalog_item_image",
        response_class=Response,
        responses={200: {"content": {"image/jpeg": {}}, "description": "Stored item image"}},
    )
    async def get_catalog_item_image(request: Request, item_id: str) -> Response:
        scope = _read_scope(request, include_retired=False)
        request.state.commercial_scope = scope
        try:
            data, content_type = await asyncio.to_thread(catalog.load_item_image, scope, item_id)
        except CatalogWriteError as exc:
            raise _refused(exc) from exc
        return Response(content=data, media_type=content_type)

    @router.get(
        "/availability",
        operation_id="v1_get_catalog_availability",
        response_model=ApiResponse[CatalogAvailabilityDTO],
    )
    async def get_catalog_availability(request: Request) -> ApiResponse[CatalogAvailabilityDTO]:
        principal = authorize_admin_request(request, "catalog.availability.read")
        scope = scope_from_admin_principal(principal)
        request.state.commercial_scope = scope
        state = await asyncio.to_thread(catalog.get_availability, scope)
        return ApiResponse(data=catalog_availability_dto(state), meta=_meta(request))

    @router.put(
        "/availability",
        operation_id="v1_save_catalog_availability",
        response_model=ApiResponse[CatalogAvailabilityDTO],
    )
    async def save_catalog_availability(
        request: Request,
        payload: CatalogAvailabilityCommandDTO,
    ) -> ApiResponse[CatalogAvailabilityDTO]:
        principal = authorize_admin_request(request, "catalog.availability.write")
        scope = scope_from_admin_principal(principal)
        request.state.commercial_scope = scope
        check_rate_limit(request, "v1_catalog_availability_update", limit=60)
        state = await asyncio.to_thread(
            catalog.save_availability,
            scope,
            {
                "service_period": payload.service_period,
                "service_periods": (
                    {name: window.model_dump() for name, window in payload.service_periods.items()}
                    if payload.service_periods is not None
                    else None
                ),
                "sold_out_item_ids": payload.sold_out_item_ids,
                "low_stock_item_ids": payload.low_stock_item_ids,
                # The stored row still calls this `store_disabled_item_ids`;
                # the published contract uses the domain's word.
                "store_disabled_item_ids": payload.disabled_item_ids,
            },
        )
        await asyncio.to_thread(
            operations.record_admin_action,
            "admin_availability.update",
            target_type="availability",
            target_id=str(scope.store_id),
            request=request,
            metadata={"actor_type": "manager"},
            scope=scope,
        )
        return ApiResponse(data=catalog_availability_dto(state), meta=_meta(request))

    return router
