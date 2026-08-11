"""Capability-centered `/api/v1/catalog` transport.

The routes live in the legacy transport layer for now because a capability
package may not import `services` or `utils`, and admin scope resolution still
lives there. The contract is already capability-shaped, so moving the file
later does not move the API.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from api.v1.catalog_contracts import CatalogItemDTO, CatalogItemListDTO, catalog_item_dto
from api.v1.contracts import ApiErrorResponse, ApiMeta, ApiResponse
from capabilities import catalog
from models.commercial_scope import CommercialScope
from services.commercial_context_service import scope_from_admin_principal, scope_from_device_principal
from utils.auth_utils import authorize_admin_request, require_kiosk_token
from utils.commercial_scope_config import resolve_commercial_scope


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=str(request.state.request_id), timestamp=datetime.now(timezone.utc))


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

    return router
