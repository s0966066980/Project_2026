"""Admin-facing structured promotion management.

Promotions are stored as JSON source documents under rag_documents/promotions.
The recommendation engine reads the same files through rag_offer_service, so
this service only validates and writes the source records.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config
from repositories import menu_repository


VALID_STATUSES = {"active", "draft", "inactive"}
VALID_TYPE = "promotion"
PROMOTION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,80}$")


def _documents_root() -> Path:
    configured = Path(config.RAG_DOCUMENTS_DIR)
    base = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return configured.resolve() if configured.is_absolute() else (base / configured).resolve()


def _promotions_root() -> Path:
    return _documents_root() / "promotions"


def _promotion_path(offer_id: str) -> Path:
    return _promotions_root() / f"{offer_id}.json"


def _promotion_file_for_offer(offer_id: str) -> Path | None:
    normalized = _safe_text(offer_id, 90)
    if not PROMOTION_ID_PATTERN.match(normalized):
        return None
    direct_path = _promotion_path(normalized)
    if direct_path.exists():
        return direct_path
    root = _promotions_root()
    if not root.exists():
        return None
    for path in sorted(root.glob("*.json")):
        record = _load_json(path)
        if not record:
            continue
        candidates = {
            str(record.get("offer_id") or "").strip(),
            str(record.get("source_id") or "").strip(),
            path.stem,
        }
        if normalized in candidates:
            return path
    return None


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


def _parse_date(value: Any) -> str:
    text = _safe_text(value, 40)
    if not text:
        return ""
    if len(text) == 10:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    datetime.fromisoformat(text.replace("Z", "+00:00"))
    return text


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
    item_ids = {
        str(item.get("id") or "").strip()
        for item in menu_rows
        if str(item.get("id") or "").strip()
    }
    categories = {
        str(item.get("category") or "").strip()
        for item in menu_rows
        if str(item.get("category") or "").strip()
    }
    return item_ids, categories


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, list):
        return dict(data[0]) if data and isinstance(data[0], dict) else {}
    return dict(data) if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".json.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def validate_promotion_payload(payload: dict, *, existing_offer_id: str = "") -> tuple[dict | None, list[str]]:
    raw = payload if isinstance(payload, dict) else {}
    offer_id = _safe_text(raw.get("offer_id") or existing_offer_id, 90)
    errors = []
    if not PROMOTION_ID_PATTERN.match(offer_id):
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
        valid_from = _parse_date(raw.get("valid_from") or raw.get("starts_at"))
    except ValueError:
        valid_from = ""
        errors.append("valid_from 日期格式錯誤，請使用 YYYY-MM-DD 或 ISO datetime")
    try:
        valid_until = _parse_date(raw.get("valid_until") or raw.get("ends_at"))
    except ValueError:
        valid_until = ""
        errors.append("valid_until 日期格式錯誤，請使用 YYYY-MM-DD 或 ISO datetime")
    if valid_from and valid_until and valid_from > valid_until:
        errors.append("valid_from 不可晚於 valid_until")

    valid_item_ids, valid_categories = _menu_lookup()
    item_ids = [item_id for item_id in _as_list(raw.get("item_ids") or raw.get("items")) if item_id in valid_item_ids]
    categories = [category for category in _as_list(raw.get("categories") or raw.get("category")) if category in valid_categories]
    required_cart_item_ids = [
        item_id
        for item_id in _as_list(raw.get("required_cart_item_ids") or raw.get("required_items"))
        if item_id in valid_item_ids
    ]
    if not item_ids and not categories:
        errors.append("至少需要一個有效 item_ids 或 categories")

    invalid_items = sorted(set(_as_list(raw.get("item_ids") or raw.get("items"))) - valid_item_ids)
    invalid_required = sorted(set(_as_list(raw.get("required_cart_item_ids") or raw.get("required_items"))) - valid_item_ids)
    invalid_categories = sorted(set(_as_list(raw.get("categories") or raw.get("category"))) - valid_categories)
    if invalid_items:
        errors.append(f"item_ids 不存在：{', '.join(invalid_items[:8])}")
    if invalid_required:
        errors.append(f"required_cart_item_ids 不存在：{', '.join(invalid_required[:8])}")
    if invalid_categories:
        errors.append(f"categories 不存在：{', '.join(invalid_categories[:8])}")

    if errors:
        return None, errors

    source_id = _safe_text(raw.get("source_id") or f"promotion_{offer_id}", 120)
    content = _safe_text(raw.get("content") or raw.get("description"), 1000)
    record = {
        "type": VALID_TYPE,
        "offer_id": offer_id,
        "source_id": source_id,
        "source_type": "promotion",
        "status": status,
        "title": title,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "timezone": timezone_name,
        "member_only": _as_bool(raw.get("member_only")),
        "item_ids": item_ids,
        "categories": categories,
        "required_cart_item_ids": required_cart_item_ids,
        "score_boost": _as_int(raw.get("score_boost"), int(config.get("RECOMMENDATION_RAG_OFFER_WEIGHT", 4))),
        "category_score_boost": _as_int(
            raw.get("category_score_boost"),
            int(config.get("RECOMMENDATION_RAG_CATEGORY_WEIGHT", 2)),
        ),
        "content": content,
        "metadata": {
            "category": _safe_text((raw.get("metadata") or {}).get("category") if isinstance(raw.get("metadata"), dict) else "", 80) or "promotion",
            "status": status,
        },
    }
    return record, []


def list_promotions() -> list[dict]:
    root = _promotions_root()
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.glob("*.json")):
        record = _load_json(path)
        if not record:
            continue
        record["path"] = path.name
        rows.append(record)
    return rows


def get_promotion(offer_id: str) -> dict | None:
    normalized = _safe_text(offer_id, 90)
    if not PROMOTION_ID_PATTERN.match(normalized):
        return None
    path = _promotion_file_for_offer(normalized)
    if not path:
        return None
    record = _load_json(path)
    if record:
        record["path"] = path.name
    return record or None


def save_promotion(payload: dict, *, existing_offer_id: str = "") -> tuple[dict | None, list[str]]:
    record, errors = validate_promotion_payload(payload, existing_offer_id=existing_offer_id)
    if errors or not record:
        return None, errors
    if existing_offer_id and record["offer_id"] != existing_offer_id:
        return None, ["不可修改 offer_id，請建立新活動"]
    _write_json(_promotion_path(record["offer_id"]), record)
    return record, []


def update_promotion_status(offer_id: str, status: str) -> tuple[dict | None, list[str]]:
    record = get_promotion(offer_id)
    if not record:
        return None, ["找不到活動"]
    next_status = _safe_text(status, 20).lower()
    if next_status not in VALID_STATUSES:
        return None, ["status 必須為 active、draft 或 inactive"]
    path = _promotion_file_for_offer(offer_id)
    if not path:
        return None, ["找不到活動"]
    record["status"] = next_status
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    metadata["status"] = next_status
    record["metadata"] = metadata
    record.pop("path", None)
    _write_json(path, record)
    record["path"] = path.name
    return record, []


def delete_promotion(offer_id: str) -> bool:
    normalized = _safe_text(offer_id, 90)
    if not PROMOTION_ID_PATTERN.match(normalized):
        return False
    path = _promotion_file_for_offer(normalized)
    if not path:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
