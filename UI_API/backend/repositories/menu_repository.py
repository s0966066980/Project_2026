"""Store-scoped menu catalog repository (ADR-0018).

PostgreSQL is the runtime master when enabled. Without Postgres, a scoped JSON
document under learning data is used so unit tests stay offline. Empty stores
seed once from MENU_JSON_PATH and are never overwritten by the seed file.
"""

from __future__ import annotations

import json
import os
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import config
from models.commercial_scope import CommercialScope
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope

_menu_cache = None
_menu_cache_mtime = None

CORE_FIELDS = frozenset({"id", "name", "category", "price", "description", "image", "retired_at", "retired"})


def _store_menu_json_path() -> str:
    return os.path.join(config.LEARNING_DATA_DIR, "store_menu_items.json")


def _scope_key(scope: CommercialScope) -> str:
    return f"{scope.tenant_id}:{scope.store_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_item(raw: dict, *, item_id: str | None = None) -> dict:
    source = raw if isinstance(raw, dict) else {}
    resolved_id = _text(item_id or source.get("id"))
    extra = source.get("extra") if isinstance(source.get("extra"), dict) else {}
    # Preserve unknown seed fields in extra when not already nested.
    for key, value in source.items():
        if key in CORE_FIELDS or key == "extra":
            continue
        if key not in extra:
            extra[key] = value
    price_raw = source.get("price", 0)
    try:
        price = int(float(price_raw))
    except (TypeError, ValueError):
        price = 0
    retired_at = source.get("retired_at")
    if retired_at is not None:
        retired_at = _text(retired_at) or None
    row = {
        "id": resolved_id,
        "name": _text(source.get("name")) or resolved_id,
        "category": _text(source.get("category")),
        "price": price,
        "description": _text(source.get("description")),
        "image": _text(source.get("image")),
        "retired_at": retired_at,
        "extra": extra,
    }
    # Flatten common extra fields for consumers that still read top-level keys.
    for key, value in extra.items():
        if key not in row:
            row[key] = value
    return row


def _public_item(row: dict, *, include_retired_flag: bool = True) -> dict:
    item = dict(row)
    item_id = _text(item.get("id"))
    item["id"] = item_id
    if include_retired_flag:
        item["retired"] = bool(item.get("retired_at"))
    # Keep storage ref separate so later updates do not persist the public API path.
    image = _text(item.get("image"))
    item["image_storage"] = image
    if image.startswith("object:"):
        item["image_ref"] = image
        item["image"] = f"/api/v1/catalog/items/{item_id}/image"
    else:
        item["image_ref"] = ""
    return item


def _read_json_store() -> dict[str, list]:
    path = _store_menu_json_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list] = {}
    for key, rows in data.items():
        if not isinstance(rows, list):
            continue
        out[str(key)] = [_normalize_item(row) for row in rows if isinstance(row, dict)]
    return out


def _write_json_store(store: dict[str, list]) -> None:
    path = _store_menu_json_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    serializable = {}
    for key, rows in store.items():
        serializable[key] = []
        for row in rows:
            payload = {
                "id": row.get("id"),
                "name": row.get("name"),
                "category": row.get("category"),
                "price": row.get("price"),
                "description": row.get("description"),
                "image": row.get("image"),
                "retired_at": row.get("retired_at"),
                "extra": row.get("extra") if isinstance(row.get("extra"), dict) else {},
            }
            serializable[key].append(payload)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_seed_menu_from_json() -> list[dict]:
    """Read the repo seed file; never the runtime master after seed."""

    global _menu_cache, _menu_cache_mtime
    try:
        current_mtime = os.path.getmtime(config.MENU_JSON_PATH)
        if _menu_cache is not None and current_mtime == _menu_cache_mtime:
            return deepcopy(_menu_cache) if isinstance(_menu_cache, list) else []
        with open(config.MENU_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _menu_cache = data if isinstance(data, list) else []
        _menu_cache_mtime = current_mtime
        return deepcopy(_menu_cache)
    except Exception:
        return []


def count_items_scoped(scope: CommercialScope, *, include_retired: bool = True) -> int:
    rows = list_items_scoped(scope, include_retired=include_retired)
    return len(rows)


def _list_postgres(scope: CommercialScope, *, include_retired: bool) -> list[dict]:
    sql = """
        SELECT item_id, name, category, price, description, image, retired_at, extra
        FROM store_menu_items
        WHERE tenant_id = %s AND store_id = %s
    """
    if not include_retired:
        sql += " AND retired_at IS NULL"
    sql += " ORDER BY category ASC, name ASC, item_id ASC"
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (scope.tenant_id, scope.store_id))
        rows = cur.fetchall() or []
    items = []
    for row in rows:
        retired = row.get("retired_at")
        retired_at = retired.isoformat() if hasattr(retired, "isoformat") else (str(retired) if retired else None)
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}
        items.append(
            _normalize_item(
                {
                    "id": row["item_id"],
                    "name": row["name"],
                    "category": row["category"],
                    "price": row["price"],
                    "description": row["description"],
                    "image": row["image"],
                    "retired_at": retired_at,
                    "extra": extra or {},
                }
            )
        )
    return items


def _list_json(scope: CommercialScope, *, include_retired: bool) -> list[dict]:
    store = _read_json_store()
    rows = store.get(_scope_key(scope), [])
    if include_retired:
        return list(rows)
    return [row for row in rows if not row.get("retired_at")]


def list_items_scoped(scope: CommercialScope, *, include_retired: bool = False) -> list[dict]:
    if postgres_utils.use_postgres():
        rows = _list_postgres(scope, include_retired=include_retired)
    else:
        rows = _list_json(scope, include_retired=include_retired)
    return [_public_item(row) for row in rows]


def ensure_seeded_scoped(scope: CommercialScope) -> dict:
    """If the store has zero items (including retired), import menu.json once."""

    existing = list_items_scoped(scope, include_retired=True)
    if existing:
        return {"seeded": False, "count": len(existing), "skipped": True}
    seed = load_seed_menu_from_json()
    if not seed:
        return {"seeded": False, "count": 0, "skipped": False, "reason": "empty_seed"}
    inserted = replace_all_scoped(scope, seed, preserve_ids=True)
    return {"seeded": True, "count": len(inserted), "skipped": False}


def get_menu_scoped(
    scope: CommercialScope | None = None,
    *,
    include_retired: bool = False,
    ensure_seed: bool = True,
) -> list:
    resolved = scope or resolve_commercial_scope()
    if ensure_seed:
        ensure_seeded_scoped(resolved)
    return list_items_scoped(resolved, include_retired=include_retired)


def get_menu() -> list:
    """Runtime catalog for the resolved commercial scope (expand-compatible entry)."""

    return get_menu_scoped(resolve_commercial_scope(), include_retired=False, ensure_seed=True)


def get_item_scoped(scope: CommercialScope, item_id: str, *, include_retired: bool = True) -> dict | None:
    target = _text(item_id)
    if not target:
        return None
    for row in list_items_scoped(scope, include_retired=include_retired):
        if _text(row.get("id")) == target:
            return row
    return None


def _generate_item_id() -> str:
    return f"itm_{secrets.token_hex(8)}"


def create_item_scoped(scope: CommercialScope, payload: dict) -> dict:
    source = payload if isinstance(payload, dict) else {}
    item_id = _text(source.get("id")) or _generate_item_id()
    if get_item_scoped(scope, item_id, include_retired=True):
        # Collision on generated id is rare; retry once for system ids.
        if not _text(source.get("id")):
            item_id = _generate_item_id()
        else:
            raise ValueError("duplicate_item_id")
    row = _normalize_item(
        {
            "id": item_id,
            "name": source.get("name"),
            "category": source.get("category"),
            "price": source.get("price"),
            "description": source.get("description"),
            "image": source.get("image"),
            "retired_at": None,
            "extra": source.get("extra") if isinstance(source.get("extra"), dict) else {},
        },
        item_id=item_id,
    )
    _upsert_item(scope, row)
    return get_item_scoped(scope, item_id) or _public_item(row)


def update_item_scoped(scope: CommercialScope, item_id: str, payload: dict) -> dict:
    existing = get_item_scoped(scope, item_id, include_retired=True)
    if existing is None:
        raise KeyError("item_not_found")
    source = payload if isinstance(payload, dict) else {}
    stored_image = _text(existing.get("image_storage") or existing.get("image_ref") or existing.get("image"))
    if stored_image.startswith(("/api/menu/items/", "/api/v1/catalog/items/")):
        stored_image = _text(existing.get("image_storage") or existing.get("image_ref"))
    next_image = source.get("image", stored_image)
    if isinstance(next_image, str) and next_image.startswith(("/api/menu/items/", "/api/v1/catalog/items/")):
        next_image = stored_image
    # Identity is immutable after create.
    merged = {
        "id": _text(item_id),
        "name": source.get("name", existing.get("name")),
        "category": source.get("category", existing.get("category")),
        "price": source.get("price", existing.get("price")),
        "description": source.get("description", existing.get("description")),
        "image": next_image,
        "retired_at": existing.get("retired_at"),
        "extra": existing.get("extra") if isinstance(existing.get("extra"), dict) else {},
    }
    if isinstance(source.get("extra"), dict):
        merged["extra"] = {**merged["extra"], **source["extra"]}
    row = _normalize_item(merged, item_id=_text(item_id))
    _upsert_item(scope, row)
    return get_item_scoped(scope, item_id, include_retired=True) or _public_item(row)


def retire_item_scoped(scope: CommercialScope, item_id: str) -> dict:
    existing = get_item_scoped(scope, item_id, include_retired=True)
    if existing is None:
        raise KeyError("item_not_found")
    if existing.get("retired_at"):
        return existing
    stored = {
        "id": _text(item_id),
        "name": existing.get("name"),
        "category": existing.get("category"),
        "price": existing.get("price"),
        "description": existing.get("description"),
        "image": existing.get("image_storage") or existing.get("image_ref") or existing.get("image"),
        "retired_at": _now_iso(),
        "extra": existing.get("extra") if isinstance(existing.get("extra"), dict) else {},
    }
    _upsert_item(scope, _normalize_item(stored, item_id=_text(item_id)))
    return get_item_scoped(scope, item_id, include_retired=True) or _public_item(stored)


def restore_item_scoped(scope: CommercialScope, item_id: str) -> dict:
    existing = get_item_scoped(scope, item_id, include_retired=True)
    if existing is None:
        raise KeyError("item_not_found")
    stored = {
        "id": _text(item_id),
        "name": existing.get("name"),
        "category": existing.get("category"),
        "price": existing.get("price"),
        "description": existing.get("description"),
        "image": existing.get("image_storage") or existing.get("image_ref") or existing.get("image"),
        "retired_at": None,
        "extra": existing.get("extra") if isinstance(existing.get("extra"), dict) else {},
    }
    _upsert_item(scope, _normalize_item(stored, item_id=_text(item_id)))
    return get_item_scoped(scope, item_id, include_retired=True) or _public_item(stored)


def _upsert_item(scope: CommercialScope, row: dict) -> None:
    if postgres_utils.use_postgres():
        _upsert_postgres(scope, row)
    else:
        _upsert_json(scope, row)


def _upsert_postgres(scope: CommercialScope, row: dict) -> None:
    item_id = _text(row.get("id"))
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    retired_at = row.get("retired_at") or None
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO store_menu_items (
                id, tenant_id, store_id, item_id, name, category, price,
                description, image, retired_at, extra, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW()
            )
            ON CONFLICT (tenant_id, store_id, item_id) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                price = EXCLUDED.price,
                description = EXCLUDED.description,
                image = EXCLUDED.image,
                retired_at = EXCLUDED.retired_at,
                extra = EXCLUDED.extra,
                updated_at = NOW()
            """,
            (
                str(uuid4()),
                scope.tenant_id,
                scope.store_id,
                item_id,
                row.get("name") or item_id,
                row.get("category") or "",
                int(row.get("price") or 0),
                row.get("description") or "",
                row.get("image") or "",
                retired_at,
                json.dumps(extra, ensure_ascii=False),
            ),
        )
        conn.commit()


def _upsert_json(scope: CommercialScope, row: dict) -> None:
    store = _read_json_store()
    key = _scope_key(scope)
    rows = store.get(key, [])
    item_id = _text(row.get("id"))
    next_rows = []
    replaced = False
    for existing in rows:
        if _text(existing.get("id")) == item_id:
            next_rows.append(row)
            replaced = True
        else:
            next_rows.append(existing)
    if not replaced:
        next_rows.append(row)
    store[key] = next_rows
    _write_json_store(store)


def replace_all_scoped(scope: CommercialScope, items: list, *, preserve_ids: bool = True) -> list[dict]:
    """Replace the entire active catalog for a store (seed / bulk admin)."""

    normalized = []
    seen = set()
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        item_id = _text(raw.get("id"))
        if not preserve_ids or not item_id:
            item_id = _generate_item_id()
        if item_id in seen:
            continue
        seen.add(item_id)
        normalized.append(_normalize_item({**raw, "retired_at": raw.get("retired_at")}, item_id=item_id))

    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM store_menu_items WHERE tenant_id = %s AND store_id = %s",
                (scope.tenant_id, scope.store_id),
            )
            for row in normalized:
                extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
                cur.execute(
                    """
                    INSERT INTO store_menu_items (
                        id, tenant_id, store_id, item_id, name, category, price,
                        description, image, retired_at, extra, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW()
                    )
                    """,
                    (
                        str(uuid4()),
                        scope.tenant_id,
                        scope.store_id,
                        row["id"],
                        row.get("name") or row["id"],
                        row.get("category") or "",
                        int(row.get("price") or 1),
                        row.get("description") or "",
                        row.get("image") or "",
                        row.get("retired_at") or None,
                        json.dumps(extra, ensure_ascii=False),
                    ),
                )
            conn.commit()
    else:
        store = _read_json_store()
        store[_scope_key(scope)] = normalized
        _write_json_store(store)
    return list_items_scoped(scope, include_retired=True)


def reset_for_tests() -> None:
    """Clear JSON scoped store and seed cache (unit tests)."""

    global _menu_cache, _menu_cache_mtime
    _menu_cache = None
    _menu_cache_mtime = None
    path = _store_menu_json_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
