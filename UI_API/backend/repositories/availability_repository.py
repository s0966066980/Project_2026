"""Store-level menu availability repository."""

import json
import os
from copy import deepcopy
from typing import cast

import config
from models.commercial_scope import CommercialScope, is_legacy_store_scope
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope

AVAILABILITY_PATH = os.path.join(config.LEARNING_DATA_DIR, "availability.json")

DEFAULT_AVAILABILITY = {
    "store_id": "default",
    "service_period": "auto",
    "service_periods": {
        "breakfast": {"start": "05:00", "end": "10:30"},
        "regular": {"start": "10:30", "end": "23:59"},
    },
    "sold_out_item_ids": [],
    "low_stock_item_ids": [],
    "store_disabled_item_ids": [],
}


def _clean_ids(values) -> list[str]:
    seen = set()
    rows = []
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append(normalized)
    return rows


def _normalize_periods(value) -> dict:
    source: dict = value if isinstance(value, dict) else {}
    default_periods = cast(dict, DEFAULT_AVAILABILITY["service_periods"])
    periods = {}
    for key in ("breakfast", "regular"):
        raw_row = source.get(key)
        row: dict = raw_row if isinstance(raw_row, dict) else {}
        periods[key] = {
            "start": str(row.get("start") or default_periods[key]["start"]).strip(),
            "end": str(row.get("end") or default_periods[key]["end"]).strip(),
        }
    return periods


def normalize_availability(data: dict | None) -> dict:
    source = data if isinstance(data, dict) else {}
    row = deepcopy(DEFAULT_AVAILABILITY)
    row["store_id"] = str(source.get("store_id") or row["store_id"]).strip() or "default"
    period = str(source.get("service_period") or row["service_period"]).strip().lower()
    row["service_period"] = period if period in ("auto", "breakfast", "regular") else "auto"
    row["service_periods"] = _normalize_periods(source.get("service_periods"))
    row["sold_out_item_ids"] = _clean_ids(source.get("sold_out_item_ids"))
    row["low_stock_item_ids"] = _clean_ids(source.get("low_stock_item_ids"))
    row["store_disabled_item_ids"] = _clean_ids(source.get("store_disabled_item_ids"))
    return row


def _get_json_availability() -> dict:
    if not os.path.exists(AVAILABILITY_PATH):
        return deepcopy(DEFAULT_AVAILABILITY)
    try:
        with open(AVAILABILITY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return deepcopy(DEFAULT_AVAILABILITY)
    return normalize_availability(data)


def _save_json_availability(data: dict) -> dict:
    row = normalize_availability(data)
    os.makedirs(os.path.dirname(AVAILABILITY_PATH), exist_ok=True)
    tmp_path = f"{AVAILABILITY_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(row, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, AVAILABILITY_PATH)
    return row


def get_availability() -> dict:
    return get_availability_scoped(resolve_commercial_scope())


def get_availability_scoped(scope: CommercialScope) -> dict:
    if postgres_utils.use_postgres():
        postgres_utils.init_schema()
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM store_availability WHERE tenant_id = %s AND store_id = %s",
                (scope.tenant_id, scope.store_id),
            )
            row = cur.fetchone()
        return normalize_availability(row["payload"] if row else {})
    if not is_legacy_store_scope(scope):
        return deepcopy(DEFAULT_AVAILABILITY)
    return _get_json_availability()


def save_availability(data: dict) -> dict:
    return save_availability_scoped(data, resolve_commercial_scope())


def save_availability_scoped(data: dict, scope: CommercialScope) -> dict:
    row = normalize_availability(data)
    if postgres_utils.use_postgres():
        row["store_id"] = str(scope.store_id)
        from psycopg.types.json import Jsonb

        postgres_utils.init_schema()
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO store_availability (store_id, tenant_id, payload)
                VALUES (%s, %s, %s)
                ON CONFLICT (store_id) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    version = store_availability.version + 1,
                    updated_at = NOW()
                WHERE store_availability.tenant_id = EXCLUDED.tenant_id
                RETURNING store_id
                """,
                (scope.store_id, scope.tenant_id, Jsonb(row)),
            )
            if cur.fetchone() is None:
                raise ValueError("Availability store is owned by another tenant")
            conn.commit()
        return row
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON availability storage only supports the legacy Default Scope")
    return _save_json_availability(row)
