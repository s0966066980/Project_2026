"""Structured promotion signals loaded from RAG source documents.

Vector search remains useful for voice answers, but recommendation scoring needs
deterministic, validated promotion data. This service reads JSON promotion
documents from rag_documents/promotions and returns menu-safe offer signals.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config

SUPPORTED_STATUS = {"", "active", "published", "enabled"}
DISABLED_STATUS = {"example", "draft", "inactive", "disabled", "archived"}


def _documents_root() -> Path:
    configured = Path(config.RAG_DOCUMENTS_DIR)
    base = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return configured.resolve() if configured.is_absolute() else (base / configured).resolve()


def _promotions_root() -> Path:
    return _documents_root() / "promotions"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        values = [str(part or "").strip() for part in value]
    else:
        values = [str(value or "").strip()]
    seen = set()
    rows = []
    for item in values:
        if item and item not in seen:
            seen.add(item)
            rows.append(item)
    return rows


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _default_timezone_name() -> str:
    return str(config.get("PROMOTION_DEFAULT_TIMEZONE", "Asia/Taipei") or "Asia/Taipei").strip() or "Asia/Taipei"


def _promotion_timezone(row: dict) -> ZoneInfo:
    timezone_name = str(row.get("timezone") or _default_timezone_name()).strip()
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(_default_timezone_name())


def _parse_datetime(value: Any, *, end_of_day: bool = False, local_timezone: ZoneInfo | None = None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    tz = local_timezone or ZoneInfo(_default_timezone_name())
    if len(text) == 10:
        try:
            parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None
        parsed_time = time.max if end_of_day else time.min
        return datetime.combine(parsed_date, parsed_time, tzinfo=tz)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None
        parsed_time = time.max if end_of_day else time.min
        parsed = datetime.combine(parsed_date, parsed_time)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def _menu_lookup(menu_items: list[dict]) -> tuple[set[str], set[str]]:
    item_ids = {
        str(item.get("id") or "").strip()
        for item in menu_items or []
        if str(item.get("id") or "").strip()
    }
    categories = {
        str(item.get("category") or "").strip()
        for item in menu_items or []
        if str(item.get("category") or "").strip()
    }
    return item_ids, categories


def _load_json_rows(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data if isinstance(data, list) else [data]
    return [row for row in rows if isinstance(row, dict)]


def _is_active(row: dict, now: datetime) -> bool:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    status = str(row.get("status") or metadata.get("status") or "").strip().lower()
    if status in DISABLED_STATUS:
        return False
    if status not in SUPPORTED_STATUS:
        return False

    local_timezone = _promotion_timezone(row)
    current_time = now if now.tzinfo is not None else now.replace(tzinfo=local_timezone)
    starts_at = _parse_datetime(row.get("starts_at") or row.get("valid_from"), local_timezone=local_timezone)
    ends_at = _parse_datetime(row.get("ends_at") or row.get("valid_until"), end_of_day=True, local_timezone=local_timezone)
    if starts_at and current_time < starts_at:
        return False
    if ends_at and current_time > ends_at:
        return False
    return True


def _normalize_offer(row: dict, path: Path, index: int, menu_items: list[dict], now: datetime) -> dict | None:
    if str(row.get("type") or row.get("source_type") or "promotion").strip() != "promotion":
        return None
    if not _is_active(row, now):
        return None

    valid_item_ids, valid_categories = _menu_lookup(menu_items)
    item_ids = [item_id for item_id in _as_list(row.get("item_ids") or row.get("items")) if item_id in valid_item_ids]
    categories = [
        category
        for category in _as_list(row.get("categories") or row.get("category"))
        if category in valid_categories
    ]
    required_cart_item_ids = [
        item_id
        for item_id in _as_list(row.get("required_cart_item_ids") or row.get("required_items"))
        if item_id in valid_item_ids
    ]
    if not item_ids and not categories:
        return None

    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    source_id = str(row.get("source_id") or metadata.get("source_id") or f"{path.stem}_{index}").strip()
    offer_id = str(row.get("offer_id") or source_id).strip()
    title = str(row.get("title") or row.get("name") or offer_id).strip()
    score_boost = max(1, _as_int(row.get("score_boost"), int(config.get("RECOMMENDATION_RAG_OFFER_WEIGHT", 4))))
    category_score_boost = max(
        1,
        _as_int(row.get("category_score_boost"), int(config.get("RECOMMENDATION_RAG_CATEGORY_WEIGHT", 2))),
    )

    return {
        "offer_id": offer_id,
        "source_id": source_id,
        "source": "rag",
        "title": title,
        "description": str(row.get("description") or row.get("content") or "").strip(),
        "member_only": _as_bool(row.get("member_only")),
        "item_ids": item_ids,
        "categories": categories,
        "required_cart_item_ids": required_cart_item_ids,
        "score_boost": score_boost,
        "category_score_boost": category_score_boost,
        "starts_at": str(row.get("starts_at") or row.get("valid_from") or ""),
        "ends_at": str(row.get("ends_at") or row.get("valid_until") or ""),
        "timezone": str(row.get("timezone") or _default_timezone_name()),
        "path": path.name,
    }


def load_active_offers(menu_items: list[dict], *, now: datetime | None = None) -> list[dict]:
    """Return active, menu-validated promotion signals.

    Invalid files or incomplete rows are ignored so RAG content issues do not
    break Kiosk recommendation flows.
    """
    if not config.get("RAG_ENABLED", False):
        return []
    root = _promotions_root()
    if not root.exists():
        return []
    current_time = now or datetime.now(timezone.utc)
    offers = []
    for path in sorted(root.glob("*.json")):
        for index, row in enumerate(_load_json_rows(path)):
            offer = _normalize_offer(row, path, index, menu_items, current_time)
            if offer:
                offers.append(offer)
    return offers


def format_offer_prompt_section(offers: list[dict], *, audience: str = "guest", limit: int = 5) -> str:
    visible_offers = []
    for offer in offers or []:
        if offer.get("member_only") and audience != "member":
            continue
        visible_offers.append(offer)
    if not visible_offers:
        return ""
    lines = ["【已驗證 RAG 優惠】"]
    for offer in visible_offers[:limit]:
        scope = "會員專屬" if offer.get("member_only") else "一般活動"
        targets = ", ".join(offer.get("item_ids") or offer.get("categories") or [])
        lines.append(f"- {offer.get('title', '')}｜{scope}｜適用品項/分類：{targets}")
    lines.append("優惠、折扣、加購價與活動期間只能依據本段已列出的 verified offers；沒有列出的優惠不可自行編造。")
    lines.append("若顧客詢問未列出的優惠，請回答目前沒有查到可確認的活動，並以現場公告或結帳畫面為準。")
    return "\n".join(lines)
