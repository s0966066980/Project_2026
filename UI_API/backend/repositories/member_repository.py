import json
import os
import threading
from datetime import datetime

import config
from repositories import postgres_utils

MEMBERS_PATH = os.path.join(config.LEARNING_DATA_DIR, "members.json")

_lock = threading.Lock()


def _read() -> list:
    try:
        with open(MEMBERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(rows: list) -> list:
    parent = os.path.dirname(MEMBERS_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f"{MEMBERS_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, MEMBERS_PATH)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return rows


def _dual_write_enabled() -> bool:
    return bool(config.get("ENABLE_MEMBER_DUAL_WRITE", False))


def _mask_phone(phone) -> str:
    value = str(phone or "")
    if len(value) != 10:
        return value
    return f"{value[:4]}-***-{value[7:]}"


def _jsonb(value, default):
    try:
        from psycopg.types.json import Jsonb
    except Exception as exc:
        raise postgres_utils.PostgresUnavailableError("psycopg Jsonb support is required") from exc
    return Jsonb(value if isinstance(value, type(default)) else default)


def _order_item_rows(order: dict) -> list[dict]:
    cart_items = order.get("cart_items")
    if isinstance(cart_items, list) and cart_items:
        rows = []
        for item in cart_items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                continue
            try:
                quantity = int(item.get("quantity", item.get("qty", 1)) or 1)
            except Exception:
                quantity = 1
            try:
                unit_price = int(float(item.get("price") or 0))
            except Exception:
                unit_price = 0
            rows.append({
                "item_id": item_id,
                "item_name": str(item.get("name") or ""),
                "category": str(item.get("category") or ""),
                "quantity": max(1, quantity),
                "unit_price": unit_price,
            })
        if rows:
            return rows

    counts = {}
    for item_id in order.get("cart_ids") or []:
        normalized = str(item_id or "").strip()
        if normalized:
            counts[normalized] = counts.get(normalized, 0) + 1
    return [
        {
            "item_id": item_id,
            "item_name": "",
            "category": "",
            "quantity": quantity,
            "unit_price": 0,
        }
        for item_id, quantity in counts.items()
    ]


def _postgres_upsert_member(record: dict) -> dict:
    postgres_utils.init_schema()
    phone = str(record.get("phone") or "").strip()
    if not phone:
        return record
    now = datetime.now().isoformat()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO members (
                    phone, phone_masked, nickname, created_at, updated_at,
                    visit_count, total_spend, last_visit_at,
                    last_login_at, login_count, login_failed_count,
                    consent_version, privacy_version, consent_accepted_at, consent_source,
                    order_history_consent, personalization_consent,
                    data_retention_until, deleted_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone) DO UPDATE SET
                    phone_masked = EXCLUDED.phone_masked,
                    nickname = EXCLUDED.nickname,
                    updated_at = EXCLUDED.updated_at,
                    visit_count = EXCLUDED.visit_count,
                    total_spend = EXCLUDED.total_spend,
                    last_visit_at = EXCLUDED.last_visit_at,
                    last_login_at = EXCLUDED.last_login_at,
                    login_count = EXCLUDED.login_count,
                    login_failed_count = EXCLUDED.login_failed_count,
                    consent_version = EXCLUDED.consent_version,
                    privacy_version = EXCLUDED.privacy_version,
                    consent_accepted_at = EXCLUDED.consent_accepted_at,
                    consent_source = EXCLUDED.consent_source,
                    order_history_consent = EXCLUDED.order_history_consent,
                    personalization_consent = EXCLUDED.personalization_consent,
                    data_retention_until = EXCLUDED.data_retention_until,
                    deleted_at = EXCLUDED.deleted_at
                """,
                (
                    phone,
                    _mask_phone(phone),
                    str(record.get("nickname") or ""),
                    str(record.get("created_at") or now),
                    now,
                    int(record.get("visit_count", 0) or 0),
                    int(record.get("total_spend", 0) or 0),
                    str(record.get("last_visit_at") or ""),
                    str(record.get("last_login_at") or ""),
                    int(record.get("login_count", 0) or 0),
                    int(record.get("login_failed_count", 0) or 0),
                    str(record.get("consent_version") or ""),
                    str(record.get("privacy_version") or ""),
                    str(record.get("consent_accepted_at") or ""),
                    str(record.get("consent_source") or ""),
                    bool(record.get("order_history_consent", False)),
                    bool(record.get("personalization_consent", False)),
                    str(record.get("data_retention_until") or ""),
                    str(record.get("deleted_at") or ""),
                ),
            )
            cur.execute(
                """
                INSERT INTO member_preferences (
                    phone, item_freq, category_freq, pair_freq,
                    recent_item_ids, preference_updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone) DO UPDATE SET
                    item_freq = EXCLUDED.item_freq,
                    category_freq = EXCLUDED.category_freq,
                    pair_freq = EXCLUDED.pair_freq,
                    recent_item_ids = EXCLUDED.recent_item_ids,
                    preference_updated_at = EXCLUDED.preference_updated_at
                """,
                (
                    phone,
                    _jsonb(record.get("item_freq"), {}),
                    _jsonb(record.get("category_freq"), {}),
                    _jsonb(record.get("pair_freq"), {}),
                    _jsonb(record.get("recent_item_ids"), []),
                    str(record.get("preference_updated_at") or ""),
                ),
            )
            cur.execute("DELETE FROM member_orders WHERE phone = %s", (phone,))
            for index, order in enumerate(record.get("orders") or []):
                if not isinstance(order, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO member_orders (
                        phone, order_index, session_id, timestamp, total,
                        order_status, is_completed, cancel_reason,
                        recommendation_success, is_success, cart_ids, cart_items
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        phone,
                        index,
                        str(order.get("session_id") or ""),
                        str(order.get("timestamp") or ""),
                        int(order.get("total", 0) or 0),
                        str(order.get("order_status") or "completed"),
                        bool(order.get("is_completed", True)),
                        str(order.get("cancel_reason") or ""),
                        bool(order.get("recommendation_success", order.get("is_success", False))),
                        bool(order.get("is_success", order.get("recommendation_success", False))),
                        _jsonb(order.get("cart_ids"), []),
                        _jsonb(order.get("cart_items"), []),
                    ),
                )
                order_id = cur.fetchone()["id"]
                for item in _order_item_rows(order):
                    cur.execute(
                        """
                        INSERT INTO member_order_items (
                            order_id, item_id, item_name, category, quantity, unit_price
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            order_id,
                            item["item_id"],
                            item["item_name"],
                            item["category"],
                            item["quantity"],
                            item["unit_price"],
                        ),
                    )
        conn.commit()
    return record


def _postgres_record_from_rows(member_row: dict, preference_row: dict | None, order_rows: list[dict]) -> dict:
    record = {
        "phone": str(member_row.get("phone") or ""),
        "nickname": str(member_row.get("nickname") or ""),
        "created_at": str(member_row.get("created_at") or ""),
        "visit_count": int(member_row.get("visit_count", 0) or 0),
        "total_spend": int(member_row.get("total_spend", 0) or 0),
        "last_visit_at": str(member_row.get("last_visit_at") or ""),
        "last_login_at": str(member_row.get("last_login_at") or ""),
        "login_count": int(member_row.get("login_count", 0) or 0),
        "login_failed_count": int(member_row.get("login_failed_count", 0) or 0),
        "consent_version": str(member_row.get("consent_version") or ""),
        "privacy_version": str(member_row.get("privacy_version") or ""),
        "consent_accepted_at": str(member_row.get("consent_accepted_at") or ""),
        "consent_source": str(member_row.get("consent_source") or ""),
        "order_history_consent": bool(member_row.get("order_history_consent", False)),
        "personalization_consent": bool(member_row.get("personalization_consent", False)),
        "data_retention_until": str(member_row.get("data_retention_until") or ""),
        "deleted_at": str(member_row.get("deleted_at") or ""),
        "item_freq": {},
        "category_freq": {},
        "pair_freq": {},
        "recent_item_ids": [],
        "preference_updated_at": "",
        "orders": [],
    }
    if preference_row:
        record.update({
            "item_freq": preference_row.get("item_freq") or {},
            "category_freq": preference_row.get("category_freq") or {},
            "pair_freq": preference_row.get("pair_freq") or {},
            "recent_item_ids": preference_row.get("recent_item_ids") or [],
            "preference_updated_at": str(preference_row.get("preference_updated_at") or ""),
        })
    record["orders"] = [
        {
            "session_id": str(row.get("session_id") or ""),
            "timestamp": str(row.get("timestamp") or ""),
            "cart_ids": row.get("cart_ids") or [],
            "cart_items": row.get("cart_items") or [],
            "total": int(row.get("total", 0) or 0),
            "order_status": str(row.get("order_status") or "completed"),
            "is_completed": bool(row.get("is_completed", True)),
            "cancel_reason": str(row.get("cancel_reason") or ""),
            "recommendation_success": bool(row.get("recommendation_success", False)),
            "is_success": bool(row.get("is_success", False)),
        }
        for row in order_rows
    ]
    return record


def _postgres_get_member(phone: str) -> dict | None:
    postgres_utils.init_schema()
    key = str(phone or "")
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM members WHERE phone = %s", (key,))
            member_row = cur.fetchone()
            if not member_row:
                return None
            cur.execute("SELECT * FROM member_preferences WHERE phone = %s", (key,))
            preference_row = cur.fetchone()
            cur.execute(
                "SELECT * FROM member_orders WHERE phone = %s ORDER BY order_index ASC, id ASC",
                (key,),
            )
            order_rows = cur.fetchall()
    return _postgres_record_from_rows(member_row, preference_row, order_rows)


def _postgres_get_all_members() -> list:
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT phone FROM members ORDER BY created_at ASC, phone ASC")
            phones = [row["phone"] for row in cur.fetchall()]
    rows = []
    for phone in phones:
        record = _postgres_get_member(phone)
        if record:
            rows.append(record)
    return rows


def _postgres_delete_member(phone: str) -> bool:
    postgres_utils.init_schema()
    key = str(phone or "")
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM members WHERE phone = %s", (key,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def _safe_postgres_write(operation, *args):
    try:
        return operation(*args)
    except Exception:
        return None


def get_all_members() -> list:
    if postgres_utils.use_postgres():
        try:
            return _postgres_get_all_members()
        except Exception:
            pass
    with _lock:
        return _read()


def get_member(phone: str) -> dict | None:
    if postgres_utils.use_postgres():
        try:
            return _postgres_get_member(phone)
        except Exception:
            pass
    key = str(phone or "")
    with _lock:
        for row in _read():
            if str(row.get("phone")) == key:
                return row
    return None


def upsert_member(record: dict) -> dict:
    if postgres_utils.use_postgres():
        try:
            return _postgres_upsert_member(record)
        except Exception:
            pass
    key = str(record.get("phone") or "")
    with _lock:
        rows = _read()
        for i, row in enumerate(rows):
            if str(row.get("phone")) == key:
                rows[i] = record
                break
        else:
            rows.append(record)
        _write(rows)
    if _dual_write_enabled():
        _safe_postgres_write(_postgres_upsert_member, record)
    return record


def delete_member(phone: str) -> bool:
    if postgres_utils.use_postgres():
        try:
            return _postgres_delete_member(phone)
        except Exception:
            pass
    key = str(phone or "")
    with _lock:
        rows = _read()
        kept = [r for r in rows if str(r.get("phone")) != key]
        if len(kept) == len(rows):
            return False
        _write(kept)
    if _dual_write_enabled():
        _safe_postgres_write(_postgres_delete_member, phone)
    return True
