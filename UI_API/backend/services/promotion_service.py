"""Admin-facing structured promotion management.

Promotions are stored as JSON source documents under rag_documents/promotions.
The recommendation engine reads the same files through rag_offer_service, so
this service only validates and writes the source records.
"""

from __future__ import annotations

import re
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config
from models.commercial_scope import CommercialScope
from repositories import menu_repository, promotion_repository

VALID_STATUSES = {"active", "draft", "inactive"}
VALID_TYPE = "promotion"
PROMOTION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,80}$")
VALID_SURFACES = {"recommendation", "pos_home_banner", "kiosk_cart_banner"}
VALID_TARGET_TYPES = {"category", "item", "recommendation", "none"}
VALID_THEMES = {"gold", "red", "dark", "simple"}


def is_valid_promotion_id(value: str) -> bool:
    return bool(PROMOTION_ID_PATTERN.match(str(value or "").strip()))


def _safe_text(value: Any, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


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
        text = _safe_text(raw, limit)
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _as_int(value: Any, default: int = 1, minimum: int = 1, maximum: int = 20) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _as_optional_int(value: Any, *, minimum: int = 0, maximum: int = 9999) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(minimum, min(maximum, number))


def _as_optional_positive_int(value: Any, *, minimum: int = 1, maximum: int = 3600) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(minimum, min(maximum, number))


def _first_filled(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _parse_date(value: Any) -> str:
    text = _safe_text(value, 40)
    if not text:
        return ""
    if len(text) == 10:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    datetime.fromisoformat(text.replace("Z", "+00:00"))
    return text


def _parse_datetime(value: Any, *, timezone_name: str, end_of_day: bool = False) -> datetime | None:
    text = _safe_text(value, 40)
    if not text:
        return None
    local_timezone = ZoneInfo(timezone_name)
    if len(text) == 10:
        parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
        parsed_time = time.max if end_of_day else time.min
        return datetime.combine(parsed_date, parsed_time, tzinfo=local_timezone)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_timezone)
    return parsed


def _default_timezone() -> str:
    return str(config.get("PROMOTION_DEFAULT_TIMEZONE", "Asia/Taipei") or "Asia/Taipei").strip() or "Asia/Taipei"


def _parse_timezone(value: Any) -> str:
    text = _safe_text(value, 80) or _default_timezone()
    try:
        ZoneInfo(text)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone 不存在，請使用 IANA timezone，例如 Asia/Taipei") from exc
    return text


def _menu_lookup() -> tuple[set[str], set[str]]:
    menu_rows = menu_repository.get_menu()
    item_ids = {str(item.get("id") or "").strip() for item in menu_rows if str(item.get("id") or "").strip()}
    categories = {
        str(item.get("category") or "").strip() for item in menu_rows if str(item.get("category") or "").strip()
    }
    return item_ids, categories


def validate_promotion_payload(payload: dict, *, existing_offer_id: str = "") -> tuple[dict | None, list[str]]:
    raw = payload if isinstance(payload, dict) else {}
    offer_id = _safe_text(raw.get("offer_id") or raw.get("id") or existing_offer_id, 90)
    errors = []
    if not is_valid_promotion_id(offer_id):
        errors.append("offer_id 必須為 3-81 字元，只能使用英數、底線或連字號，且需以英數開頭")

    title = _safe_text(raw.get("title") or raw.get("name"), 120)
    if not title:
        errors.append("title 不可為空")

    status = _safe_text(raw.get("status") or "draft", 20).lower()
    if status not in VALID_STATUSES:
        errors.append("status 必須為 active、draft 或 inactive")

    try:
        timezone_name = _parse_timezone(raw.get("timezone"))
    except ValueError as exc:
        timezone_name = _default_timezone()
        errors.append(str(exc))

    try:
        start_at = _parse_date(raw.get("start_at") or raw.get("starts_at") or raw.get("valid_from"))
    except ValueError:
        start_at = ""
        errors.append("start_at 日期格式錯誤，請使用 YYYY-MM-DD 或 ISO datetime")
    try:
        end_at = _parse_date(raw.get("end_at") or raw.get("ends_at") or raw.get("valid_until"))
    except ValueError:
        end_at = ""
        errors.append("end_at 日期格式錯誤，請使用 YYYY-MM-DD 或 ISO datetime")
    try:
        start_dt = _parse_datetime(start_at, timezone_name=timezone_name) if start_at else None
        end_dt = _parse_datetime(end_at, timezone_name=timezone_name, end_of_day=True) if end_at else None
    except ValueError:
        start_dt = None
        end_dt = None
        errors.append("活動日期格式錯誤，請使用 YYYY-MM-DD 或 ISO datetime")
    if start_dt and end_dt and start_dt > end_dt:
        errors.append("end_at 不可早於 start_at")

    valid_item_ids, valid_categories = _menu_lookup()
    surface = _safe_text(raw.get("surface") or "recommendation", 40)
    if surface not in VALID_SURFACES:
        errors.append("surface 必須為 recommendation、pos_home_banner 或 kiosk_cart_banner")
    target_type = _safe_text(raw.get("target_type") or "none", 40)
    if target_type not in VALID_TARGET_TYPES:
        errors.append("target_type 必須為 category、item、recommendation 或 none")
    target_value = _safe_text(raw.get("target_value"), 120)
    if target_type == "category":
        if not target_value:
            errors.append("target_type 為 category 時 target_value 不可為空")
        elif target_value not in valid_categories:
            errors.append(f"target_value 分類不存在：{target_value}")
    if target_type == "item":
        if not target_value:
            errors.append("target_type 為 item 時 target_value 不可為空")
        elif target_value not in valid_item_ids:
            errors.append(f"target_value 品項不存在：{target_value}")
    item_ids = [item_id for item_id in _as_list(raw.get("item_ids") or raw.get("items")) if item_id in valid_item_ids]
    categories = [
        category for category in _as_list(raw.get("categories") or raw.get("category")) if category in valid_categories
    ]
    required_cart_item_ids = [
        item_id
        for item_id in _as_list(raw.get("required_cart_item_ids") or raw.get("required_items"))
        if item_id in valid_item_ids
    ]
    if not item_ids and not categories and surface != "pos_home_banner":
        errors.append("至少需要一個有效 item_ids 或 categories")

    invalid_items = sorted(set(_as_list(raw.get("item_ids") or raw.get("items"))) - valid_item_ids)
    invalid_required = sorted(
        set(_as_list(raw.get("required_cart_item_ids") or raw.get("required_items"))) - valid_item_ids
    )
    invalid_categories = sorted(set(_as_list(raw.get("categories") or raw.get("category"))) - valid_categories)
    if invalid_items:
        errors.append(f"item_ids 不存在：{', '.join(invalid_items[:8])}")
    if invalid_required:
        errors.append(f"required_cart_item_ids 不存在：{', '.join(invalid_required[:8])}")
    if invalid_categories:
        errors.append(f"categories 不存在：{', '.join(invalid_categories[:8])}")

    if errors:
        return None, errors

    pricing_raw = raw.get("pricing") if isinstance(raw.get("pricing"), dict) else {}
    pricing_type = _safe_text(raw.get("pricing_type") or pricing_raw.get("type") or "none", 40)
    original_price = _as_optional_int(_first_filled(raw.get("original_price"), pricing_raw.get("original_price")))
    promotion_price = _as_optional_int(
        _first_filled(raw.get("promo_price"), raw.get("promotion_price"), pricing_raw.get("promotion_price"))
    )
    pricing = {}
    if promotion_price is not None:
        if promotion_price <= 0:
            errors.append("promotion_price 必須大於 0")
        if original_price is not None and original_price < promotion_price:
            errors.append("original_price 不可小於 promotion_price")
        pricing = {
            "type": pricing_type if pricing_type != "none" else "add_on_fixed_price",
            "original_price": original_price,
            "promotion_price": promotion_price,
            "currency": _safe_text(raw.get("currency") or pricing_raw.get("currency") or "TWD", 12),
        }
    if errors:
        return None, errors

    ad_raw = raw.get("ad") if isinstance(raw.get("ad"), dict) else {}
    ad_cta = _first_filled(raw.get("cta_text"), raw.get("ad_cta"), ad_raw.get("cta"))
    badge = _safe_text(raw.get("badge") or raw.get("ad_headline") or ad_raw.get("headline"), 80)
    subtitle = _safe_text(raw.get("subtitle") or raw.get("ad_copy") or ad_raw.get("copy"), 160)
    ad = {
        "headline": badge,
        "copy": subtitle,
        "cta": _safe_text(ad_cta or "加入優惠", 40),
    }
    if not (ad["headline"] or ad["copy"] or ad_cta):
        ad = {}

    theme = _safe_text(raw.get("theme") or "gold", 24)
    if theme not in VALID_THEMES:
        errors.append("theme 必須為 gold、red、dark 或 simple")
    if errors:
        return None, errors

    source_id = _safe_text(raw.get("source_id") or f"promotion_{offer_id}", 120)
    content = _safe_text(raw.get("content") or raw.get("description"), 1000)
    now_text = datetime.now(ZoneInfo(timezone_name)).isoformat()
    record = {
        "id": offer_id,
        "type": VALID_TYPE,
        "offer_id": offer_id,
        "source_id": source_id,
        "source_type": "promotion",
        "enabled": _as_bool(_first_filled(raw.get("enabled"), True)),
        "surface": surface,
        "priority": _as_int(raw.get("priority"), default=0, minimum=0, maximum=1000),
        "rotation_seconds": _as_optional_positive_int(raw.get("rotation_seconds"), minimum=2, maximum=120),
        "status": status,
        "title": title,
        "subtitle": subtitle,
        "description": content,
        "valid_from": start_at,
        "valid_until": end_at,
        "start_at": start_at,
        "end_at": end_at,
        "timezone": timezone_name,
        "member_only": _as_bool(raw.get("member_only")),
        "badge": badge,
        "original_price": original_price,
        "promo_price": promotion_price,
        "save_text": _safe_text(raw.get("save_text"), 40),
        "cta_text": _safe_text(ad_cta or "加入優惠", 40),
        "target_type": target_type,
        "target_value": target_value,
        "theme": theme,
        "legal_text": _safe_text(raw.get("legal_text"), 180),
        "item_ids": item_ids,
        "categories": categories,
        "required_cart_item_ids": required_cart_item_ids,
        "score_boost": _as_int(raw.get("score_boost"), int(config.get("RECOMMENDATION_RAG_OFFER_WEIGHT", 4))),
        "category_score_boost": _as_int(
            raw.get("category_score_boost"),
            int(config.get("RECOMMENDATION_RAG_CATEGORY_WEIGHT", 2)),
        ),
        "pricing": pricing,
        "ad": ad,
        "content": content,
        "created_at": _safe_text(raw.get("created_at"), 40) or now_text,
        "updated_at": now_text,
        "metadata": {
            "category": _safe_text(
                (raw.get("metadata") or {}).get("category") if isinstance(raw.get("metadata"), dict) else "", 80
            )
            or "promotion",
            "status": status,
        },
    }
    return record, []


def list_promotions(scope: CommercialScope | None = None) -> list[dict]:
    if scope is not None:
        return promotion_repository.list_promotions_scoped(scope)
    return promotion_repository.list_promotions()


def get_promotion(offer_id: str, scope: CommercialScope | None = None) -> dict | None:
    normalized = _safe_text(offer_id, 90)
    if not is_valid_promotion_id(normalized):
        return None
    if scope is not None:
        return promotion_repository.get_promotion_scoped(normalized, scope, is_valid_id=is_valid_promotion_id)
    return promotion_repository.get_promotion(normalized, is_valid_id=is_valid_promotion_id)


def save_promotion(
    payload: dict,
    *,
    existing_offer_id: str = "",
    scope: CommercialScope | None = None,
) -> tuple[dict | None, list[str]]:
    record, errors = validate_promotion_payload(payload, existing_offer_id=existing_offer_id)
    if errors or not record:
        return None, errors
    if existing_offer_id and record["offer_id"] != existing_offer_id:
        return None, ["不可修改 offer_id，請建立新活動"]
    existing = get_promotion(record["offer_id"], scope)
    if existing and existing.get("created_at"):
        record["created_at"] = existing["created_at"]
    if scope is None:
        promotion_repository.save_promotion(record["offer_id"], record)
    else:
        promotion_repository.save_promotion_scoped(record["offer_id"], record, scope)
    return record, []


def update_promotion_status(
    offer_id: str,
    status: str,
    scope: CommercialScope | None = None,
) -> tuple[dict | None, list[str]]:
    record = get_promotion(offer_id, scope)
    if not record:
        return None, ["找不到活動"]
    next_status = _safe_text(status, 20).lower()
    if next_status not in VALID_STATUSES:
        return None, ["status 必須為 active、draft 或 inactive"]
    record["status"] = next_status
    record["enabled"] = next_status == "active"
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    metadata["status"] = next_status
    record["metadata"] = metadata
    record.pop("path", None)
    timezone_name = str(record.get("timezone") or _default_timezone())
    record["updated_at"] = datetime.now(ZoneInfo(timezone_name)).isoformat()
    if scope is not None:
        promotion_repository.save_promotion_scoped(offer_id, record, scope)
    else:
        path = promotion_repository.find_promotion_path(offer_id, is_valid_id=is_valid_promotion_id)
        if path:
            promotion_repository.save_promotion_at_path(path, record)
            record["path"] = path.name
        else:
            promotion_repository.save_promotion(str(record.get("offer_id") or offer_id), record)
            record["path"] = f"{record.get('offer_id') or offer_id}.json"
    return record, []


def delete_promotion(offer_id: str, scope: CommercialScope | None = None) -> bool:
    normalized = _safe_text(offer_id, 90)
    if not is_valid_promotion_id(normalized):
        return False
    if scope is not None:
        return promotion_repository.delete_promotion_scoped(normalized, scope, is_valid_id=is_valid_promotion_id)
    return promotion_repository.delete_promotion(normalized, is_valid_id=is_valid_promotion_id)
