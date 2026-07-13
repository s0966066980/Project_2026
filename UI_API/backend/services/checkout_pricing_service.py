"""Authoritative checkout cart validation and promotion pricing."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config
from models.commercial_scope import CommercialScope
from repositories import menu_repository
from services import promotion_service

ACTIVE_PROMOTION_STATUSES = {"active", "published", "enabled"}


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


def _as_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([value] if value not in (None, "") else [])
    return [str(item or "").strip() for item in values if str(item or "").strip()]


def _promotion_timezone(row: dict) -> ZoneInfo:
    name = str(row.get("timezone") or config.get("PROMOTION_DEFAULT_TIMEZONE", "Asia/Taipei") or "Asia/Taipei")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Taipei")


def _parse_datetime(value: Any, *, local_timezone: ZoneInfo, end_of_day: bool = False) -> datetime | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    if len(text_value) == 10:
        try:
            parsed_date = datetime.strptime(text_value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CartValidationError("promotion_invalid", "promotion date is invalid") from exc
        return datetime.combine(parsed_date, time.max if end_of_day else time.min, tzinfo=local_timezone)
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CartValidationError("promotion_invalid", "promotion date is invalid") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=local_timezone)


def _promotion_is_active(row: dict, now: datetime) -> bool:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    status = str(row.get("status") or metadata.get("status") or "").strip().lower()
    if status not in ACTIVE_PROMOTION_STATUSES or row.get("enabled") is False:
        return False
    local_timezone = _promotion_timezone(row)
    current_time = now if now.tzinfo is not None else now.replace(tzinfo=local_timezone)
    starts_at = _parse_datetime(
        row.get("start_at") or row.get("starts_at") or row.get("valid_from"),
        local_timezone=local_timezone,
    )
    ends_at = _parse_datetime(
        row.get("end_at") or row.get("ends_at") or row.get("valid_until"),
        local_timezone=local_timezone,
        end_of_day=True,
    )
    return not ((starts_at and current_time < starts_at) or (ends_at and current_time > ends_at))


def _promotion_targets_item(row: dict, menu_item: dict) -> bool:
    item_id = str(menu_item.get("id") or "")
    category = str(menu_item.get("category") or "")
    if item_id in _as_list(row.get("item_ids") or row.get("items")):
        return True
    if category and category in _as_list(row.get("categories") or row.get("category")):
        return True
    target_type = str(row.get("target_type") or "none").strip()
    target_value = str(row.get("target_value") or "").strip()
    return (target_type == "item" and target_value == item_id) or (
        target_type == "category" and target_value == category
    )


def _promotion_price(row: dict, base_price: int) -> int:
    pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
    raw = row.get("promo_price") or row.get("promotion_price") or pricing.get("promotion_price")
    try:
        promotion_price = int(float(raw))
    except (TypeError, ValueError) as exc:
        raise CartValidationError("promotion_price_invalid", "promotion price is invalid") from exc
    if promotion_price <= 0 or promotion_price > base_price:
        raise CartValidationError("promotion_price_invalid", "promotion price exceeds the menu price")
    return promotion_price


def _source_rows(cart_items: Any, cart_ids: Any) -> list[dict]:
    if isinstance(cart_items, list) and cart_items:
        return cart_items
    if isinstance(cart_ids, list):
        return [{"id": item_id, "quantity": 1} for item_id in cart_ids]
    return []


def price_checkout_cart(
    cart_items: Any,
    cart_ids: Any,
    *,
    is_member: bool,
    now: datetime | None = None,
    scope: CommercialScope | None = None,
) -> dict:
    menu_by_id = {
        str(item.get("id") or "").strip(): item
        for item in menu_repository.get_menu()
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    source_rows = _source_rows(cart_items, cart_ids)
    if not source_rows:
        raise CartValidationError("empty_cart", "cart is empty")

    normalized_sources: list[tuple[dict, int, str]] = []
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
        quantity = _positive_quantity(raw.get("quantity", raw.get("qty", 1)))
        offer_id = str(raw.get("applied_offer_id") or "").strip()
        previous_offer = seen_offers.get(item_id)
        if previous_offer is not None and previous_offer != offer_id:
            raise CartValidationError("conflicting_promotions", "one item cannot use multiple promotions")
        seen_offers[item_id] = offer_id
        total_quantity += quantity
        if total_quantity > 100:
            raise CartValidationError("cart_too_large", "cart exceeds 100 items")
        submitted_ids.add(item_id)
        normalized_sources.append((menu_item, quantity, offer_id))

    current_time = now or datetime.now(timezone.utc)
    normalized_by_id: dict[str, dict] = {}
    order: list[str] = []
    for menu_item, quantity, offer_id in normalized_sources:
        item_id = str(menu_item.get("id"))
        base_price = _price(menu_item.get("price"))
        final_price = base_price
        promotion_title = ""
        if offer_id:
            promotion = (
                promotion_service.get_promotion(offer_id, scope)
                if scope
                else promotion_service.get_promotion(offer_id)
            )
            if not promotion or not _promotion_is_active(promotion, current_time):
                raise CartValidationError("promotion_not_active", "promotion is not active")
            if promotion.get("member_only") and not is_member:
                raise CartValidationError("member_required", "promotion requires a member")
            required_ids = set(_as_list(
                promotion.get("required_cart_item_ids") or promotion.get("required_items")
            ))
            if not required_ids.issubset(submitted_ids):
                raise CartValidationError(
                    "promotion_requirements_not_met",
                    "required cart items are missing",
                )
            if not _promotion_targets_item(promotion, menu_item):
                raise CartValidationError("promotion_target_mismatch", "promotion does not target this item")
            final_price = _promotion_price(promotion, base_price)
            promotion_title = str(promotion.get("title") or offer_id).strip()

        existing = normalized_by_id.get(item_id)
        if existing:
            existing["quantity"] += quantity
            continue
        order.append(item_id)
        row = {
            "id": item_id,
            "name": str(menu_item.get("name") or item_id),
            "category": str(menu_item.get("category") or ""),
            "price": final_price,
            "quantity": quantity,
        }
        if offer_id:
            row.update({
                "original_price": base_price,
                "applied_offer_id": offer_id,
                "offer_ids": [offer_id],
                "promotion_title": promotion_title,
            })
        normalized_by_id[item_id] = row

    normalized = [normalized_by_id[item_id] for item_id in order]
    return {
        "cart_ids": order,
        "cart_items": normalized,
        "total": sum(int(item["price"]) * int(item["quantity"]) for item in normalized),
    }
