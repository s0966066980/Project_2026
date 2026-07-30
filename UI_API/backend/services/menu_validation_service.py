"""Validation for administrator-managed menu documents."""

from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse


MENU_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
UNSAFE_ATTRIBUTE_CHARS = re.compile(r"[\x00-\x1f\x7f\"'<>`]")


class MenuValidationError(ValueError):
    def __init__(self, message: str, *, index: int | None = None, field: str = ""):
        super().__init__(message)
        self.index = index
        self.field = field


def _text(value: Any, *, field: str, index: int, maximum: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise MenuValidationError(f"{field} is required", index=index, field=field)
    if len(text) > maximum:
        raise MenuValidationError(f"{field} is too long", index=index, field=field)
    return text


def _validate_image_url(value: Any, *, index: int) -> str:
    image = _text(value, field="image", index=index, maximum=2048)
    if not image:
        return ""
    if UNSAFE_ATTRIBUTE_CHARS.search(image):
        raise MenuValidationError("image contains unsafe characters", index=index, field="image")
    if image.startswith("/static/"):
        return image
    if image.startswith("object:") and len(image) <= 512:
        return image
    parsed = urlparse(image)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MenuValidationError("image must use http(s), /static/, or object:", index=index, field="image")
    if parsed.username or parsed.password:
        raise MenuValidationError("image credentials are not allowed", index=index, field="image")
    return image


def _validate_price(value: Any, *, index: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MenuValidationError("price must be numeric", index=index, field="price") from exc
    if not math.isfinite(number) or number <= 0 or number > 100_000 or not number.is_integer():
        raise MenuValidationError("price must be an integer between 1 and 100000", index=index, field="price")
    return int(number)


def validate_menu_payload(payload: Any) -> list[dict]:
    if not isinstance(payload, list):
        raise MenuValidationError("menu payload must be a list")
    if len(payload) > 1000:
        raise MenuValidationError("menu payload exceeds 1000 items")

    validated: list[dict] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise MenuValidationError("menu item must be an object", index=index)
        item_id = _text(raw.get("id"), field="id", index=index, maximum=80, required=True)
        if not MENU_ID_PATTERN.fullmatch(item_id):
            raise MenuValidationError("id contains invalid characters", index=index, field="id")
        if item_id in seen_ids:
            raise MenuValidationError("duplicate menu id", index=index, field="id")
        seen_ids.add(item_id)

        row = dict(raw)
        row["id"] = item_id
        row["name"] = _text(raw.get("name"), field="name", index=index, maximum=160, required=True)
        row["category"] = _text(raw.get("category"), field="category", index=index, maximum=100, required=True)
        row["price"] = _validate_price(raw.get("price"), index=index)
        row["image"] = _validate_image_url(raw.get("image"), index=index)
        if "emoji" in raw:
            emoji = _text(raw.get("emoji"), field="emoji", index=index, maximum=16)
            if UNSAFE_ATTRIBUTE_CHARS.search(emoji):
                raise MenuValidationError("emoji contains unsafe characters", index=index, field="emoji")
            row["emoji"] = emoji
        validated.append(row)
    return validated
