"""Pre-authored AI push copy per menu item, scoped per store.

Two slots per item. Base copy is evergreen and never asserts a promotion; campaign copy is
optional and names the offer it depends on, so it stops being served once that offer ends.
The runtime never generates copy — see docs/adr/0016-author-push-copy-ahead-of-time.md.
"""

import json
import os
from datetime import date
from uuid import uuid4

import config
from models.commercial_scope import CommercialScope, is_legacy_store_scope
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope

PUSH_COPY_PATH = os.path.join(config.LEARNING_DATA_DIR, "push_copy.json")

_FIELDS = ("base_copy", "campaign_copy", "campaign_offer_id", "is_new_item", "new_until")


def _text(value) -> str:
    return str(value or "").strip()


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    raw = _text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def normalize_entry(data: dict | None) -> dict:
    source = data if isinstance(data, dict) else {}
    new_until = _parse_date(source.get("new_until"))
    return {
        "base_copy": _text(source.get("base_copy")),
        "campaign_copy": _text(source.get("campaign_copy")),
        "campaign_offer_id": _text(source.get("campaign_offer_id")),
        "is_new_item": bool(source.get("is_new_item")),
        "new_until": new_until.isoformat() if new_until else "",
    }


def is_currently_new(entry: dict, today: date | None = None) -> bool:
    """New-item status expires by date, so a forgotten tick stops counting on its own."""

    if not entry.get("is_new_item"):
        return False
    until = _parse_date(entry.get("new_until"))
    if until is None:
        return True
    return (today or date.today()) <= until


def _json_all() -> dict:
    if not os.path.exists(PUSH_COPY_PATH):
        return {}
    try:
        with open(PUSH_COPY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): normalize_entry(v) for k, v in data.items() if _text(k)}


def _json_save_all(rows: dict) -> None:
    os.makedirs(os.path.dirname(PUSH_COPY_PATH), exist_ok=True)
    tmp_path = f"{PUSH_COPY_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, PUSH_COPY_PATH)


def list_copy() -> dict:
    return list_copy_scoped(resolve_commercial_scope())


def list_copy_scoped(scope: CommercialScope) -> dict:
    """Return {item_id: entry} for the scope. Missing items simply have no key."""

    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT item_id, base_copy, campaign_copy, campaign_offer_id, is_new_item, new_until
                FROM menu_item_push_copy
                WHERE tenant_id = %s AND store_id = %s
                """,
                (scope.tenant_id, scope.store_id),
            )
            rows = cur.fetchall()
        return {str(row["item_id"]): normalize_entry(dict(row)) for row in rows}
    if not is_legacy_store_scope(scope):
        return {}
    return _json_all()


def save_copy_scoped(
    item_id: str,
    entry: dict,
    scope: CommercialScope,
    *,
    actor_id: str = "",
) -> dict:
    key = _text(item_id)
    if not key:
        raise ValueError("item_id is required")
    row = normalize_entry(entry)
    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO menu_item_push_copy (
                    id, tenant_id, store_id, item_id,
                    base_copy, campaign_copy, campaign_offer_id, is_new_item, new_until, actor_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, store_id, item_id) DO UPDATE SET
                    base_copy = EXCLUDED.base_copy,
                    campaign_copy = EXCLUDED.campaign_copy,
                    campaign_offer_id = EXCLUDED.campaign_offer_id,
                    is_new_item = EXCLUDED.is_new_item,
                    new_until = EXCLUDED.new_until,
                    actor_id = EXCLUDED.actor_id,
                    updated_at = NOW()
                """,
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.store_id,
                    key,
                    row["base_copy"],
                    row["campaign_copy"],
                    row["campaign_offer_id"],
                    row["is_new_item"],
                    _parse_date(row["new_until"]),
                    _text(actor_id),
                ),
            )
            conn.commit()
        return row
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON push copy storage only supports the legacy Default Scope")
    rows = _json_all()
    rows[key] = row
    _json_save_all(rows)
    return row
