"""Authoritative checkout cart validation and promotion pricing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from capabilities import catalog
from capabilities.campaign_promotion import (
    PromotionContext,
    promotion_service,
    quote_promotion,
    select_promotion_quote,
)
from models.commercial_scope import CommercialScope

# availability_service stays in services/ on purpose: the context it builds is
# shared with recommendation, so it is a cross-capability dependency rather
# than this capability's private implementation. Tracked as shared
# infrastructure, not as an ordering tail.
from modules.checkout_confirmation import _pricing_shadow as commercial_shadow_service
from services import availability_service

CHECKOUT_CALCULATION_VERSION = "checkout-v1"
CHECKOUT_CURRENCY = "TWD"


class CartValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _positive_quantity(value: Any) -> int:
    try:
        quantity = int(value)
    except (TypeError, ValueError) as exc:
        raise CartValidationError("invalid_quantity", "quantity must be an integer") from exc
    if quantity < 1 or quantity > 20:
        raise CartValidationError("invalid_quantity", "quantity must be between 1 and 20")
    return quantity


def _price(value: Any) -> int:
    try:
        price = int(float(value))
    except (TypeError, ValueError) as exc:
        raise CartValidationError("invalid_menu_price", "menu price is invalid") from exc
    if price <= 0 or price > 100_000:
        raise CartValidationError("invalid_menu_price", "menu price is outside the accepted range")
    return price


def _source_rows(cart_items: Any, cart_ids: Any) -> list[dict]:
    if isinstance(cart_items, list) and cart_items:
        return cart_items
    if isinstance(cart_ids, list):
        return [{"id": item_id, "quantity": 1} for item_id in cart_ids]
    return []


def _price_options(raw: Any, menu_item: dict) -> tuple[list[dict], int]:
    selections = raw if isinstance(raw, list) else ([] if raw in (None, "") else None)
    if selections is None:
        raise CartValidationError("invalid_options", "options must be a list")
    catalog = {
        str(option.get("id") or "").strip(): option
        for option in (menu_item.get("options") or [])
        if isinstance(option, dict) and str(option.get("id") or "").strip()
    }
    snapshots: list[dict] = []
    total = 0
    for selection in selections:
        option_id = str(selection.get("id") if isinstance(selection, dict) else selection).strip()
        option = catalog.get(option_id)
        if option is None:
            raise CartValidationError("unknown_option", "selected option is unavailable")
        try:
            option_price = int(option.get("price") or 0)
        except (TypeError, ValueError) as exc:
            raise CartValidationError("invalid_option_price", "option price is invalid") from exc
        if option_price < 0 or option_price > 100_000:
            raise CartValidationError("invalid_option_price", "option price is outside the accepted range")
        snapshots.append({"id": option_id, "name": str(option.get("name") or option_id), "price": option_price})
        total += option_price
    return snapshots, total


def price_checkout_cart(
    cart_items: Any,
    cart_ids: Any,
    *,
    is_member: bool,
    now: datetime | None = None,
    scope: CommercialScope | None = None,
) -> dict:
    if scope is not None:
        menu_rows = catalog.list_items(scope, include_retired=False, ensure_seed=True)
    else:
        menu_rows = catalog.list_active_items()
    menu_by_id = {
        str(item.get("id") or "").strip(): item
        for item in menu_rows
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    availability = availability_service.build_availability_context(
        list(menu_by_id.values()),
        now=now,
        scope=scope,
    )
    exclude_ids = {
        str(item_id).strip() for item_id in (availability.get("exclude_item_ids") or []) if str(item_id).strip()
    }
    sold_out_ids = {
        str(item_id).strip() for item_id in (availability.get("sold_out_item_ids") or []) if str(item_id).strip()
    }
    disabled_ids = {
        str(item_id).strip() for item_id in (availability.get("store_disabled_item_ids") or []) if str(item_id).strip()
    }
    time_unavailable_ids = {
        str(item_id).strip()
        for item_id in (availability.get("time_unavailable_item_ids") or [])
        if str(item_id).strip()
    }
    source_rows = _source_rows(cart_items, cart_ids)
    if not source_rows:
        raise CartValidationError("empty_cart", "cart is empty")

    normalized_sources: list[tuple[dict, int, str, list[dict], int]] = []
    submitted_ids: set[str] = set()
    seen_offers: dict[str, str] = {}
    total_quantity = 0
    for raw in source_rows:
        if not isinstance(raw, dict):
            raise CartValidationError("invalid_cart_item", "cart item must be an object")
        item_id = str(raw.get("id") or "").strip()
        menu_item = menu_by_id.get(item_id)
        if not menu_item:
            raise CartValidationError("unknown_item", f"unknown menu item: {item_id}")
        if item_id in sold_out_ids:
            raise CartValidationError("item_sold_out", f"menu item is sold out: {item_id}")
        if item_id in disabled_ids:
            raise CartValidationError("item_disabled", f"menu item is disabled: {item_id}")
        if item_id in time_unavailable_ids:
            raise CartValidationError(
                "item_time_unavailable",
                f"menu item is not available in the current service period: {item_id}",
            )
        if item_id in exclude_ids:
            raise CartValidationError("item_unavailable", f"menu item is unavailable: {item_id}")
        quantity = _positive_quantity(raw.get("quantity", raw.get("qty", 1)))
        option_snapshots, option_unit_total = _price_options(raw.get("options"), menu_item)
        offer_id = str(raw.get("applied_offer_id") or "").strip()
        previous_offer = seen_offers.get(item_id)
        if previous_offer is not None and previous_offer != offer_id:
            raise CartValidationError("conflicting_promotions", "one item cannot use multiple promotions")
        seen_offers[item_id] = offer_id
        total_quantity += quantity
        if total_quantity > 100:
            raise CartValidationError("cart_too_large", "cart exceeds 100 items")
        submitted_ids.add(item_id)
        normalized_sources.append((menu_item, quantity, offer_id, option_snapshots, option_unit_total))

    current_time = now or datetime.now(timezone.utc)
    promotions = promotion_service.list_promotions(scope)
    normalized_by_id: dict[str, dict] = {}
    order: list[str] = []
    for menu_item, quantity, offer_id, option_snapshots, option_unit_total in normalized_sources:
        item_id = str(menu_item.get("id"))
        base_price = _price(menu_item.get("price"))
        final_price = base_price
        promotion_title = ""
        applied_offer_id = ""
        promotion_context = PromotionContext(
            now=current_time,
            is_member=is_member,
            item_id=item_id,
            category=str(menu_item.get("category") or ""),
            cart_item_ids=frozenset(submitted_ids),
            scope=scope,
        )
        candidate_promotions = promotions
        legacy_ref = ""
        legacy_effective_price = base_price
        if offer_id:
            requested = (
                promotion_service.get_promotion(offer_id, scope) if scope else promotion_service.get_promotion(offer_id)
            )
            requested_quote = quote_promotion(requested or {}, promotion_context, base_price=base_price)
            if not requested or not requested_quote.eligible:
                error_codes = {
                    "member_required": "member_required",
                    "requirements_not_met": "promotion_requirements_not_met",
                    "target_mismatch": "promotion_target_mismatch",
                    "promotion_price_invalid": "promotion_price_invalid",
                }
                code = error_codes.get(requested_quote.code, "promotion_not_active")
                raise CartValidationError(code, requested_quote.code)
            legacy_ref = requested_quote.promotion_ref
            legacy_effective_price = requested_quote.effective_price
            if requested not in candidate_promotions:
                candidate_promotions = [*candidate_promotions, requested]

        selected_quote = select_promotion_quote(
            candidate_promotions,
            promotion_context,
            base_price=base_price,
            preferred_ref=offer_id,
        )
        if selected_quote.eligible:
            final_price = selected_quote.effective_price
            applied_offer_id = selected_quote.promotion_ref
            promotion_title = selected_quote.promotion_title
        commercial_shadow_service.compare_pricing(
            preferred_ref=offer_id,
            legacy_ref=legacy_ref,
            legacy_effective_price=legacy_effective_price,
            selected_ref=selected_quote.promotion_ref if selected_quote.eligible else "",
            selected_effective_price=selected_quote.effective_price if selected_quote.eligible else base_price,
            base_price=base_price,
        )

        variant_key = f"{item_id}:{','.join(option['id'] for option in option_snapshots)}:{applied_offer_id}"
        existing = normalized_by_id.get(variant_key)
        if existing:
            existing["quantity"] += quantity
            continue
        order.append(variant_key)
        discount_unit_total = base_price - final_price
        charged_unit_price = final_price + option_unit_total
        row = {
            "id": item_id,
            "name": str(menu_item.get("name") or item_id),
            "category": str(menu_item.get("category") or ""),
            "price": charged_unit_price,
            "quantity": quantity,
            "base_unit_price": base_price,
            "option_unit_total": option_unit_total,
            "discount_unit_total": discount_unit_total,
            "final_unit_price": charged_unit_price,
            "options": option_snapshots,
        }
        if applied_offer_id:
            row.update(
                {
                    "original_price": base_price,
                    "applied_offer_id": applied_offer_id,
                    "offer_ids": [applied_offer_id],
                    "promotion_title": promotion_title,
                    "promotion_snapshot": {
                        "promotion_ref": applied_offer_id,
                        "title": promotion_title,
                        "discount_unit_total": discount_unit_total,
                    },
                }
            )
        normalized_by_id[variant_key] = row

    normalized = [normalized_by_id[variant_key] for variant_key in order]
    subtotal = sum(int(item["base_unit_price"]) * int(item["quantity"]) for item in normalized)
    option_total = sum(int(item["option_unit_total"]) * int(item["quantity"]) for item in normalized)
    discount_total = sum(int(item["discount_unit_total"]) * int(item["quantity"]) for item in normalized)
    tax_total = 0
    total = subtotal + option_total - discount_total + tax_total
    return {
        "cart_ids": [str(item["id"]) for item in normalized],
        "cart_items": normalized,
        "subtotal": subtotal,
        "option_total": option_total,
        "discount_total": discount_total,
        "tax_total": tax_total,
        "total": total,
        "currency": CHECKOUT_CURRENCY,
        "calculation_version": CHECKOUT_CALCULATION_VERSION,
    }
