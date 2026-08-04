import json
import os
import threading
from datetime import datetime
from uuid import UUID, uuid4

import config
from models.commercial_scope import (
    CommercialScope,
    CommercialScopeConflictError,
    is_legacy_tenant_scope,
)
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope

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
    return bool(config.MEMBER_IDENTITY_DUAL_WRITE or config.get("ENABLE_MEMBER_DUAL_WRITE", False))


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
            rows.append(
                {
                    "item_id": item_id,
                    "item_name": str(item.get("name") or ""),
                    "category": str(item.get("category") or ""),
                    "quantity": max(1, quantity),
                    "unit_price": unit_price,
                }
            )
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


def _postgres_upsert_member(record: dict, scope: CommercialScope) -> dict:
    phone = str(record.get("phone") or "").strip()
    if not phone:
        return record
    now = datetime.now().isoformat()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM members WHERE tenant_id = %s AND phone = %s",
                (scope.tenant_id, phone),
            )
            existing = cur.fetchone()
            supplied_id = record.get("member_id") or record.get("id")
            member_id = UUID(str(supplied_id)) if supplied_id else (existing["id"] if existing else uuid4())
            cur.execute(
                """
                INSERT INTO members (
                    id, phone, tenant_id, phone_lookup_hash, phone_encrypted,
                    phone_masked, key_version, pii_updated_at,
                    nickname, created_at, updated_at,
                    visit_count, total_spend, last_visit_at,
                    last_login_at, login_count, login_failed_count,
                    consent_version, privacy_version, consent_accepted_at, consent_source,
                    order_history_consent, personalization_consent,
                    data_retention_until, deleted_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone, tenant_id) DO UPDATE SET
                    phone_lookup_hash = COALESCE(EXCLUDED.phone_lookup_hash, members.phone_lookup_hash),
                    phone_encrypted = COALESCE(EXCLUDED.phone_encrypted, members.phone_encrypted),
                    phone_masked = EXCLUDED.phone_masked,
                    key_version = COALESCE(EXCLUDED.key_version, members.key_version),
                    pii_updated_at = COALESCE(EXCLUDED.pii_updated_at, members.pii_updated_at),
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
                RETURNING id, tenant_id
                """,
                (
                    member_id,
                    phone,
                    scope.tenant_id,
                    str(record.get("phone_lookup_hash") or "") or None,
                    str(record.get("phone_encrypted") or "") or None,
                    str(record.get("phone_masked") or _mask_phone(phone)),
                    str(record.get("key_version") or "") or None,
                    record.get("pii_updated_at"),
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
            member_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO member_preferences (
                    member_id, tenant_id, phone, item_freq, category_freq, pair_freq,
                    recent_item_ids, preference_updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (member_id) DO UPDATE SET
                    item_freq = EXCLUDED.item_freq,
                    category_freq = EXCLUDED.category_freq,
                    pair_freq = EXCLUDED.pair_freq,
                    recent_item_ids = EXCLUDED.recent_item_ids,
                    preference_updated_at = EXCLUDED.preference_updated_at
                """,
                (
                    member_id,
                    scope.tenant_id,
                    phone,
                    _jsonb(record.get("item_freq"), {}),
                    _jsonb(record.get("category_freq"), {}),
                    _jsonb(record.get("pair_freq"), {}),
                    _jsonb(record.get("recent_item_ids"), []),
                    str(record.get("preference_updated_at") or ""),
                ),
            )
            cur.execute(
                "DELETE FROM member_orders WHERE phone = %s AND tenant_id = %s AND store_id = %s",
                (phone, scope.tenant_id, scope.store_id),
            )
            for index, order in enumerate(record.get("orders") or []):
                if not isinstance(order, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO member_orders (
                        member_id, phone, tenant_id, store_id, origin_device_id,
                        order_index, session_id, timestamp, total,
                        order_status, is_completed, cancel_reason,
                        recommendation_success, is_success, cart_ids, cart_items
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        member_id,
                        phone,
                        scope.tenant_id,
                        scope.store_id,
                        scope.device_id,
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
    result = dict(record)
    result["id"] = str(member_id)
    result["member_id"] = str(member_id)
    return result


def _postgres_record_from_rows(member_row: dict, preference_row: dict | None, order_rows: list[dict]) -> dict:
    record = {
        "id": str(member_row.get("id") or ""),
        "member_id": str(member_row.get("id") or ""),
        "phone": str(member_row.get("phone") or ""),
        "phone_masked": str(member_row.get("phone_masked") or ""),
        "key_version": str(member_row.get("key_version") or ""),
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
        record.update(
            {
                "item_freq": preference_row.get("item_freq") or {},
                "category_freq": preference_row.get("category_freq") or {},
                "pair_freq": preference_row.get("pair_freq") or {},
                "recent_item_ids": preference_row.get("recent_item_ids") or [],
                "preference_updated_at": str(preference_row.get("preference_updated_at") or ""),
            }
        )
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


def _postgres_record_for_member_row(member_row: dict, scope: CommercialScope) -> dict:
    member_id = member_row["id"]
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM member_preferences WHERE member_id = %s", (member_id,))
            preference_row = cur.fetchone()
            cur.execute(
                """SELECT * FROM member_orders
                   WHERE member_id = %s AND tenant_id = %s AND store_id = %s
                   ORDER BY order_index ASC, id ASC""",
                (member_id, scope.tenant_id, scope.store_id),
            )
            order_rows = cur.fetchall()
    return _postgres_record_from_rows(member_row, preference_row, order_rows)


def _postgres_get_member(phone: str, scope: CommercialScope) -> dict | None:
    key = str(phone or "")
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM members WHERE phone = %s AND tenant_id = %s",
                (key, scope.tenant_id),
            )
            member_row = cur.fetchone()
            if not member_row:
                return None
    return _postgres_record_for_member_row(member_row, scope)


def _postgres_get_member_by_id(member_id: UUID, scope: CommercialScope) -> dict | None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM members WHERE id = %s AND tenant_id = %s",
            (member_id, scope.tenant_id),
        )
        member_row = cur.fetchone()
    return _postgres_record_for_member_row(member_row, scope) if member_row else None


def _postgres_get_member_by_lookup_hash(lookup_hash: str, scope: CommercialScope) -> dict | None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM members WHERE tenant_id = %s AND phone_lookup_hash = %s",
            (scope.tenant_id, lookup_hash),
        )
        member_row = cur.fetchone()
    return _postgres_record_for_member_row(member_row, scope) if member_row else None


def _postgres_get_all_members(scope: CommercialScope) -> list:
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM members WHERE tenant_id = %s ORDER BY created_at ASC, id ASC",
                (scope.tenant_id,),
            )
            member_ids = [row["id"] for row in cur.fetchall()]
    rows = []
    for member_id in member_ids:
        record = _postgres_get_member_by_id(member_id, scope)
        if record:
            rows.append(record)
    return rows


def _postgres_delete_member(phone: str, scope: CommercialScope) -> bool:
    key = str(phone or "")
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM members WHERE phone = %s AND tenant_id = %s", (key, scope.tenant_id))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def _postgres_anonymize_member(member_id: UUID, scope: CommercialScope) -> bool:
    """Remove Member PII while retaining a non-identifying lifecycle record."""

    tombstone = f"deleted:{member_id}"
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM members WHERE id = %s AND tenant_id = %s FOR UPDATE",
            (member_id, scope.tenant_id),
        )
        if cur.fetchone() is None:
            return False
        for table in ("member_preferences", "member_sessions", "member_orders"):
            cur.execute(f"DELETE FROM {table} WHERE member_id = %s AND tenant_id = %s", (member_id, scope.tenant_id))
        cur.execute(
            """
            UPDATE members
            SET phone = %s,
                phone_lookup_hash = NULL,
                phone_encrypted = NULL,
                phone_masked = 'deleted',
                key_version = NULL,
                pii_updated_at = NOW(),
                anonymized_at = NOW(),
                nickname = '',
                consent_version = '',
                privacy_version = '',
                consent_accepted_at = '',
                consent_source = '',
                order_history_consent = FALSE,
                personalization_consent = FALSE,
                deleted_at = NOW()::text,
                updated_at = NOW()
            WHERE id = %s AND tenant_id = %s
            """,
            (tombstone, member_id, scope.tenant_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
    return changed


def _safe_postgres_write(operation, *args):
    try:
        return operation(*args)
    except Exception:
        return None


def get_all_members() -> list:
    return get_all_members_scoped(resolve_commercial_scope())


def get_all_members_scoped(scope: CommercialScope) -> list:
    if postgres_utils.use_postgres():
        try:
            return _postgres_get_all_members(scope)
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_tenant_scope(scope):
        return []
    with _lock:
        return _read()


def get_member(phone: str) -> dict | None:
    return get_member_scoped(phone, resolve_commercial_scope())


def get_member_by_phone_scoped(phone: str, scope: CommercialScope) -> dict | None:
    """Compatibility lookup while phone remains an accepted Kiosk input."""

    return get_member_scoped(phone, scope)


def get_member_by_id_scoped(member_id: UUID, scope: CommercialScope) -> dict | None:
    if postgres_utils.use_postgres():
        try:
            return _postgres_get_member_by_id(member_id, scope)
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_tenant_scope(scope):
        return None
    with _lock:
        for row in _read():
            if str(row.get("member_id") or row.get("id")) == str(member_id):
                return row
    return None


def get_member_by_lookup_hash_scoped(
    lookup_hash: str,
    scope: CommercialScope,
) -> dict | None:
    if postgres_utils.use_postgres():
        try:
            return _postgres_get_member_by_lookup_hash(lookup_hash, scope)
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    return None


def anonymize_member_by_id_scoped(member_id: UUID, scope: CommercialScope) -> bool:
    """Anonymize one UUID Member inside its tenant boundary."""

    if not postgres_utils.use_postgres():
        raise ValueError("Member UUID anonymization requires PostgreSQL storage")
    try:
        return _postgres_anonymize_member(member_id, scope)
    except Exception as exc:
        postgres_utils.handle_postgres_failure(exc)
    return False


def get_member_scoped(phone: str, scope: CommercialScope) -> dict | None:
    if postgres_utils.use_postgres():
        try:
            return _postgres_get_member(phone, scope)
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_tenant_scope(scope):
        return None
    key = str(phone or "")
    with _lock:
        for row in _read():
            if str(row.get("phone")) == key:
                return row
    return None


def upsert_member(record: dict) -> dict:
    return upsert_member_scoped(record, resolve_commercial_scope())


def upsert_member_scoped(record: dict, scope: CommercialScope) -> dict:
    if postgres_utils.use_postgres():
        try:
            return _postgres_upsert_member(record, scope)
        except CommercialScopeConflictError:
            raise
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_tenant_scope(scope):
        raise ValueError("JSON member storage only supports the configured legacy default scope")
    stored_record = dict(record)
    member_id = str(stored_record.get("member_id") or stored_record.get("id") or uuid4())
    stored_record["id"] = member_id
    stored_record["member_id"] = member_id
    key = str(stored_record.get("phone") or "")
    with _lock:
        rows = _read()
        for i, row in enumerate(rows):
            if str(row.get("phone")) == key:
                rows[i] = stored_record
                break
        else:
            rows.append(stored_record)
        _write(rows)
    if _dual_write_enabled():
        _safe_postgres_write(_postgres_upsert_member, stored_record, scope)
    return stored_record


def delete_member(phone: str) -> bool:
    return delete_member_scoped(phone, resolve_commercial_scope())


def delete_member_scoped(phone: str, scope: CommercialScope) -> bool:
    if postgres_utils.use_postgres():
        try:
            return _postgres_delete_member(phone, scope)
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_tenant_scope(scope):
        return False
    key = str(phone or "")
    with _lock:
        rows = _read()
        kept = [r for r in rows if str(r.get("phone")) != key]
        if len(kept) == len(rows):
            return False
        _write(kept)
    if _dual_write_enabled():
        _safe_postgres_write(_postgres_delete_member, phone, scope)
    return True
