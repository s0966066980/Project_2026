"""POS/Kiosk promotion banner selection and response shaping."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from capabilities.campaign_promotion import PromotionContext, evaluate_promotion

from models.commercial_scope import CommercialScope
from repositories import campaign_repository, promotion_repository

VALID_TARGET_TYPES = {"category", "item", "recommendation", "none"}
VALID_THEMES = {"gold", "red", "dark", "simple"}
VALID_SURFACES = {"pos_home_banner", "kiosk_cart_banner"}


def _text(value: Any, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y", "enabled", "active"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_optional_int(*values: Any) -> int | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _as_list(value: Any, *, limit: int = 80) -> list[str]:
    if value is None:
        raw_values = []
    elif isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = [value]
    rows = []
    seen = set()
    for raw in raw_values:
        text = _text(raw, limit)
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _is_active_banner(
    row: dict,
    now: datetime,
    *,
    surface: str,
    scope: CommercialScope | None = None,
) -> bool:
    return evaluate_promotion(
        row,
        PromotionContext(now=now, placement=surface, scope=scope),
    ).eligible


def _banner_item(row: dict) -> dict | None:
    title = _text(row.get("title") or row.get("name"), 120)
    if not title:
        return None
    pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
    ad = row.get("ad") if isinstance(row.get("ad"), dict) else {}
    target_type = _text(row.get("target_type"), 40) or "none"
    if target_type not in VALID_TARGET_TYPES:
        target_type = "none"
    theme = _text(row.get("theme"), 24) or "gold"
    if theme not in VALID_THEMES:
        theme = "gold"
    return {
        "id": _text(row.get("id") or row.get("offer_id") or row.get("source_id"), 90),
        "badge": _text(row.get("badge") or ad.get("headline"), 80),
        "title": title,
        "subtitle": _text(row.get("subtitle") or ad.get("copy"), 160),
        "description": _text(row.get("description") or row.get("content"), 240),
        "original_price": _as_optional_int(row.get("original_price"), pricing.get("original_price")),
        "promo_price": _as_optional_int(
            row.get("promo_price"), row.get("promotion_price"), pricing.get("promotion_price")
        ),
        "save_text": _text(row.get("save_text"), 40),
        "start_at": _text(row.get("start_at") or row.get("starts_at") or row.get("valid_from"), 40),
        "end_at": _text(row.get("end_at") or row.get("ends_at") or row.get("valid_until"), 40),
        "cta_text": _text(row.get("cta_text") or row.get("ad_cta") or ad.get("cta"), 40),
        "target_type": target_type,
        "target_value": _text(row.get("target_value"), 120),
        "theme": theme,
        "legal_text": _text(row.get("legal_text"), 180),
        "rotation_seconds": max(2, min(120, _as_int(row.get("rotation_seconds"), 6))),
        "member_only": _as_bool(row.get("member_only")),
        "item_ids": _as_list(row.get("item_ids") or row.get("items")),
        "categories": _as_list(row.get("categories") or row.get("category")),
        "required_cart_item_ids": _as_list(row.get("required_cart_item_ids") or row.get("required_items")),
    }


def get_active_pos_banners(
    *,
    now: datetime | None = None,
    limit: int = 10,
    surface: str = "pos_home_banner",
    scope: CommercialScope | None = None,
) -> list[dict]:
    selected_surface = _text(surface, 80) or "pos_home_banner"
    if selected_surface not in VALID_SURFACES:
        selected_surface = "pos_home_banner"
    current_time = now or datetime.now(timezone.utc)
    rows = []
    # Campaigns are the Admin-authored source of truth.  promotion_records is a
    # compatibility projection used by older pricing paths; an orphaned active
    # row must never become customer-visible just because it was left behind.
    active_campaign_ids = {
        str(snapshot.campaign_id)
        for snapshot in campaign_repository.default_campaign_repository.list(scope)
        if str(snapshot.status) in {"active", "scheduled"}
    }
    promotion_rows = (
        promotion_repository.list_promotions_scoped(scope) if scope else promotion_repository.list_promotions()
    )
    for row in promotion_rows:
        promotion_id = _text(row.get("id") or row.get("offer_id") or row.get("source_id"), 90)
        if promotion_id not in active_campaign_ids:
            continue
        if not _is_active_banner(row, current_time, surface=selected_surface, scope=scope):
            continue
        item = _banner_item(row)
        if item:
            rows.append((_as_int(row.get("priority"), 0), item["id"], item))
    rows.sort(key=lambda entry: (-entry[0], entry[1]))
    return [item for _, __, item in rows[: max(1, limit)]]


def get_pos_banner_response(
    *,
    now: datetime | None = None,
    surface: str = "pos_home_banner",
    scope: CommercialScope | None = None,
) -> dict:
    return {"items": get_active_pos_banners(now=now, surface=surface, scope=scope)}
