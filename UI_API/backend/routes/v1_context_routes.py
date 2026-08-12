"""Versioned compatibility endpoints grouped by capability.

These routes keep the published envelope stable while Admin/Kiosk consumers
move to their capability-owned surfaces.
"""

# Endpoint implementations share the compatibility support namespace; the
# explicit wildcard is intentional so the split modules retain one contract.
# ruff: noqa: F403, F405

from __future__ import annotations

import config
from routes.v1_support import *  # noqa: F401,F403


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Security(_document_admin_security)],
        responses={
            401: {"model": ApiErrorResponse, "description": "Authentication required"},
            403: {"model": ApiErrorResponse, "description": "Permission denied"},
            422: {"model": ApiErrorResponse, "description": "Request validation failed"},
            500: {"model": ApiErrorResponse, "description": "Safe internal error"},
        },
    )

    @router.get(
        "/public-settings",
        tags=["v1-settings"],
        operation_id="v1_get_public_settings",
        response_model=ApiResponse[dict],
    )
    async def public_settings(request: Request) -> ApiResponse[dict]:
        """Return only settings safe to broadcast to a Kiosk."""

        scope = scope_from_device_principal(require_kiosk_token(request))
        values = await asyncio.to_thread(operations.get_public_settings, scope)
        safe_values = {key: values.get(key, config.DEFAULT_SETTINGS.get(key)) for key in config.PUBLIC_SETTINGS_KEYS}
        return ApiResponse(data=safe_values, meta=_meta(request))

    @router.get(
        "/auth/me", tags=["v1-auth"], operation_id="v1_get_current_admin", response_model=ApiResponse[AdminPrincipalDTO]
    )
    async def current_admin(request: Request) -> ApiResponse[AdminPrincipalDTO]:

        principal = authorize_admin_request(request, "operations.read")

        return ApiResponse(
            data=AdminPrincipalDTO(
                user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                allowed_store_ids=list(principal.allowed_store_ids),
                roles=list(principal.roles),
                permissions=list(principal.permissions),
                session_id=principal.session_id,
                auth_method=principal.auth_method,
            ),
            meta=_meta(request),
        )

    @router.get(
        "/commercial-context",
        tags=["v1-commercial-context"],
        operation_id="v1_get_commercial_context",
        response_model=ApiResponse[CommercialContextDTO],
    )
    async def commercial_context(request: Request) -> ApiResponse[CommercialContextDTO]:

        principal = authorize_admin_request(request, "operations.read")

        scope = scope_from_admin_principal(principal)

        request.state.commercial_scope = scope

        return ApiResponse(
            data=CommercialContextDTO(
                tenant_id=scope.tenant_id, store_id=scope.store_id, device_id=scope.device_id, principal_type="admin"
            ),
            meta=_meta(request),
        )

    @router.post(
        "/cart/quote", tags=["v1-cart"], operation_id="v1_quote_cart", response_model=ApiResponse[CartQuoteDTO]
    )
    async def quote_cart(request: Request, body: CartQuoteRequest) -> ApiResponse[CartQuoteDTO]:

        principal = require_kiosk_token(request)

        scope = scope_from_device_principal(principal)

        request.state.commercial_scope = scope

        member = None

        if body.session_id:
            member = await asyncio.to_thread(member_service.get_session_member, body.session_id, scope)

        try:
            priced = await asyncio.to_thread(
                checkout_pricing_service.price_checkout_cart,
                [item.model_dump() for item in body.cart_items],
                [item.id for item in body.cart_items],
                is_member=bool(member),
                scope=scope,
            )

        except checkout_pricing_service.CartValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc

        return ApiResponse(
            data=CartQuoteDTO(
                items=[
                    CartQuoteLineDTO(
                        item_id=str(item["id"]),
                        name=str(item["name"]),
                        category=str(item.get("category") or ""),
                        quantity=int(item["quantity"]),
                        base_unit_price=int(item["base_unit_price"]),
                        effective_unit_price=int(item["final_unit_price"]),
                        option_unit_total=int(item["option_unit_total"]),
                        discount_unit_total=int(item["discount_unit_total"]),
                        activity_id=str(item.get("applied_offer_id") or ""),
                        activity_name=str(item.get("promotion_title") or ""),
                    )
                    for item in priced["cart_items"]
                ],
                subtotal=int(priced["subtotal"]),
                option_total=int(priced["option_total"]),
                discount_total=int(priced["discount_total"]),
                tax_total=int(priced["tax_total"]),
                total=int(priced["total"]),
                currency=str(priced["currency"]),
                quote_version=str(priced["calculation_version"]),
            ),
            meta=_meta(request),
        )

    @router.post(
        "/menu/price-projection",
        tags=["v1-menu"],
        operation_id="v1_project_menu_prices",
        response_model=ApiResponse[list[MenuPriceProjectionDTO]],
    )
    async def project_menu_prices(
        request: Request, body: MenuPriceProjectionRequest
    ) -> ApiResponse[list[MenuPriceProjectionDTO]]:

        principal = require_kiosk_token(request)

        scope = scope_from_device_principal(principal)

        request.state.commercial_scope = scope

        member = None

        if body.session_id:
            member = await asyncio.to_thread(member_service.get_session_member, body.session_id, scope)

        menu = await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)

        promotions = await asyncio.to_thread(promotion_service.list_promotions, scope)

        now = datetime.now(timezone.utc)

        data = []

        for item in menu:
            try:
                base_price = int(float(item.get("price") or 0))

            except (TypeError, ValueError):
                continue

            projection = project_item_price(
                promotions,
                PromotionContext(
                    now=now,
                    is_member=bool(member),
                    item_id=str(item.get("id") or ""),
                    category=str(item.get("category") or ""),
                    cart_item_ids=frozenset(body.cart_item_ids),
                    scope=scope,
                ),
                base_price=base_price,
            )

            data.append(
                MenuPriceProjectionDTO(
                    item_id=str(item.get("id") or ""),
                    base_price=projection.base_price,
                    effective_price=projection.effective_price,
                    discount=projection.discount,
                    activity_id=projection.promotion_ref,
                    activity_name=projection.promotion_title,
                    conditional=projection.conditional,
                    conditional_price=projection.conditional_price,
                    required_cart_item_ids=list(projection.required_cart_item_ids),
                )
            )

        return ApiResponse(data=data, meta=_meta(request))

    @router.post(
        "/commercial-touches",
        tags=["v1-analytics"],
        operation_id="v1_record_commercial_touch",
        response_model=ApiResponse[CommercialTouchReceiptDTO],
    )
    async def record_commercial_touch(
        request: Request, body: CommercialTouchRequest
    ) -> ApiResponse[CommercialTouchReceiptDTO]:

        principal = require_kiosk_token(request)

        scope = scope_from_device_principal(principal)

        request.state.commercial_scope = scope

        try:
            receipt = await asyncio.to_thread(record_touch, body.model_dump(), scope)

        except TouchValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": str(exc), "message": "事件資料無法接受"}) from exc

        return ApiResponse(
            data=CommercialTouchReceiptDTO(
                event_id=receipt.event_id,
                accepted=receipt.accepted,
                duplicate=receipt.duplicate,
                data_quality=receipt.data_quality,
            ),
            meta=_meta(request),
        )

    return router
