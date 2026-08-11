"""Application service for store-scoped Store Menu Item authoring (ADR-0018)."""

from __future__ import annotations

import re
from typing import Any

from models.commercial_scope import CommercialScope
from repositories import menu_repository
from services import menu_validation_service, object_storage_service
from utils.commercial_scope_config import resolve_commercial_scope

MENU_ID_PATTERN = menu_validation_service.MENU_ID_PATTERN
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_EDGE = 832


class MenuCatalogError(ValueError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _scope(scope: CommercialScope | None) -> CommercialScope:
    return scope or resolve_commercial_scope()


def list_catalog(
    scope: CommercialScope | None = None,
    *,
    include_retired: bool = False,
    ensure_seed: bool = True,
) -> list[dict]:
    return menu_repository.get_menu_scoped(
        _scope(scope),
        include_retired=include_retired,
        ensure_seed=ensure_seed,
    )


def ensure_seeded(scope: CommercialScope | None = None) -> dict:
    return menu_repository.ensure_seeded_scoped(_scope(scope))


def get_item(scope: CommercialScope | None, item_id: str, *, include_retired: bool = True) -> dict:
    row = menu_repository.get_item_scoped(_scope(scope), item_id, include_retired=include_retired)
    if row is None:
        raise MenuCatalogError("item_not_found", "menu item not found")
    return row


def _validate_authoring_fields(payload: dict, *, partial: bool = False) -> dict:
    if not isinstance(payload, dict):
        raise MenuCatalogError("invalid_payload", "payload must be an object")
    out: dict[str, Any] = {}
    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise MenuCatalogError("name_required", "name is required")
        if len(name) > 160:
            raise MenuCatalogError("name_too_long", "name is too long")
        out["name"] = name
    if not partial or "category" in payload:
        category = str(payload.get("category") or "").strip()
        if not category:
            raise MenuCatalogError("category_required", "category is required")
        if len(category) > 100:
            raise MenuCatalogError("category_too_long", "category is too long")
        out["category"] = category
    if not partial or "price" in payload:
        try:
            price = menu_validation_service._validate_price(payload.get("price"), index=0)
        except menu_validation_service.MenuValidationError as exc:
            raise MenuCatalogError("invalid_price", str(exc)) from exc
        out["price"] = price
    if not partial or "description" in payload:
        description = str(payload.get("description") or "").strip()
        if len(description) > 2000:
            raise MenuCatalogError("description_too_long", "description is too long")
        out["description"] = description
    if "image" in payload:
        try:
            out["image"] = menu_validation_service._validate_image_url(payload.get("image"), index=0)
        except menu_validation_service.MenuValidationError as exc:
            # Allow object: refs produced by upload.
            image = str(payload.get("image") or "").strip()
            if image.startswith("object:") and len(image) < 512:
                out["image"] = image
            else:
                raise MenuCatalogError("invalid_image", str(exc)) from exc
    return out


def create_item(scope: CommercialScope | None, payload: dict) -> dict:
    fields = _validate_authoring_fields(payload, partial=False)
    # Never accept client-supplied id for create (system assigns).
    return menu_repository.create_item_scoped(_scope(scope), fields)


def update_item(scope: CommercialScope | None, item_id: str, payload: dict) -> dict:
    fields = _validate_authoring_fields(payload, partial=True)
    try:
        return menu_repository.update_item_scoped(_scope(scope), item_id, fields)
    except KeyError as exc:
        raise MenuCatalogError("item_not_found", "menu item not found") from exc


def retire_item(scope: CommercialScope | None, item_id: str) -> dict:
    try:
        return menu_repository.retire_item_scoped(_scope(scope), item_id)
    except KeyError as exc:
        raise MenuCatalogError("item_not_found", "menu item not found") from exc


def restore_item(scope: CommercialScope | None, item_id: str) -> dict:
    try:
        return menu_repository.restore_item_scoped(_scope(scope), item_id)
    except KeyError as exc:
        raise MenuCatalogError("item_not_found", "menu item not found") from exc


def _normalize_image_bytes(data: bytes, content_type: str) -> bytes:
    if len(data) > MAX_UPLOAD_BYTES:
        raise MenuCatalogError("image_too_large", "image must be 5MB or smaller")
    if not data:
        raise MenuCatalogError("image_empty", "image is empty")
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in {"image/jpeg", "image/png", "image/jpg"}:
        raise MenuCatalogError("image_type_not_allowed", "only JPEG and PNG are allowed")
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise MenuCatalogError("image_processing_unavailable", "image processing is unavailable") from exc

    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise MenuCatalogError("image_invalid", "image could not be decoded")
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > MAX_IMAGE_EDGE:
        scale = MAX_IMAGE_EDGE / float(longest)
        new_w = max(1, int(round(width * scale)))
        new_h = max(1, int(round(height * scale)))
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise MenuCatalogError("image_encode_failed", "image could not be encoded")
    return encoded.tobytes()


def upload_item_image(
    scope: CommercialScope | None,
    item_id: str,
    *,
    data: bytes,
    content_type: str,
    filename: str = "upload.jpg",
) -> dict:
    resolved = _scope(scope)
    # Ensure item exists before storing bytes.
    get_item(resolved, item_id, include_retired=True)
    normalized = _normalize_image_bytes(data, content_type)
    try:
        store = object_storage_service.storage()
        meta = store.put(
            tenant_id=resolved.tenant_id,
            store_id=resolved.store_id,
            owner="menu-catalog",
            content_type="image/jpeg",
            data=normalized,
            filename=re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "item.jpg")[:80] or "item.jpg",
            retention_days=3650,
        )
        image_ref = f"object:{meta.object_id}"
    except object_storage_service.ObjectStorageError as exc:
        raise MenuCatalogError("image_storage_failed", str(exc) or "storage failed") from exc
    except Exception as exc:
        raise MenuCatalogError("image_storage_failed", "storage failed") from exc
    return update_item(resolved, item_id, {"image": image_ref})


def load_item_image_bytes(scope: CommercialScope | None, item_id: str) -> tuple[bytes, str]:
    resolved = _scope(scope)
    item = get_item(resolved, item_id, include_retired=True)
    image = str(item.get("image_storage") or item.get("image_ref") or item.get("image") or "").strip()
    if image.startswith("object:"):
        object_id = image.removeprefix("object:")
        try:
            data = object_storage_service.storage().get(object_id, tenant_id=resolved.tenant_id)
        except Exception as exc:
            raise MenuCatalogError("image_not_found", "image not found") from exc
        return data, "image/jpeg"
    if image.startswith("/static/") or image.startswith("http://") or image.startswith("https://"):
        raise MenuCatalogError("image_external", "external image; fetch the image URL directly")
    raise MenuCatalogError("image_not_found", "image not found")
