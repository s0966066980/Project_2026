"""Admin audit log repository with JSON default and optional PostgreSQL backend."""

import json
import os
import threading

import config
from models.commercial_scope import CommercialScope, CommercialScopeConflictError, is_legacy_store_scope
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope

ADMIN_AUDIT_PATH = os.path.join(config.LEARNING_DATA_DIR, "admin_audit_logs.json")

_lock = threading.Lock()


def _max_records() -> int:
    try:
        return max(100, int(config.get("ADMIN_AUDIT_MAX_RECORDS", 5000)))
    except Exception:
        return 5000


def _read() -> list:
    try:
        with open(ADMIN_AUDIT_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(rows: list) -> list:
    parent = os.path.dirname(ADMIN_AUDIT_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    trimmed = list(rows[-_max_records() :])
    tmp_path = f"{ADMIN_AUDIT_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(trimmed, handle, ensure_ascii=False, indent=4)
    os.replace(tmp_path, ADMIN_AUDIT_PATH)
    return trimmed


def _jsonb(value, default):
    try:
        from psycopg.types.json import Jsonb
    except Exception as exc:
        raise postgres_utils.PostgresUnavailableError("psycopg Jsonb support is required") from exc
    return Jsonb(value if isinstance(value, type(default)) else default)


def _postgres_append(record: dict, scope: CommercialScope) -> dict:
    postgres_utils.init_schema()
    store_id = None if "store_id" in record and record.get("store_id") is None else scope.store_id
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admin_audit_logs (
                    audit_id, tenant_id, store_id,
                    actor, action, target_type, target_id, metadata, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (audit_id) WHERE audit_id <> '' DO UPDATE SET
                    actor = EXCLUDED.actor,
                    action = EXCLUDED.action,
                    target_type = EXCLUDED.target_type,
                    target_id = EXCLUDED.target_id,
                    metadata = EXCLUDED.metadata,
                    created_at = EXCLUDED.created_at
                WHERE admin_audit_logs.tenant_id = EXCLUDED.tenant_id
                  AND admin_audit_logs.store_id IS NOT DISTINCT FROM EXCLUDED.store_id
                RETURNING audit_id
                """,
                (
                    str(record.get("audit_id") or ""),
                    scope.tenant_id,
                    store_id,
                    str(record.get("actor") or ""),
                    str(record.get("action") or ""),
                    str(record.get("target_type") or ""),
                    str(record.get("target_id") or ""),
                    _jsonb(record.get("metadata"), {}),
                    str(record.get("created_at") or ""),
                ),
            )
            if cur.fetchone() is None:
                raise CommercialScopeConflictError("Audit ID is already owned by another tenant")
        conn.commit()
    return record


def append_admin_audit(record: dict) -> dict:
    return append_admin_audit_scoped(record, resolve_commercial_scope())


def append_admin_audit_scoped(record: dict, scope: CommercialScope) -> dict:
    if postgres_utils.use_postgres():
        try:
            return _postgres_append(dict(record or {}), scope)
        except CommercialScopeConflictError:
            raise
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON audit storage only supports the configured legacy default scope")
    with _lock:
        rows = _read()
        rows.append(dict(record or {}))
        _write(rows)
    return record


def get_admin_audits(limit: int = 200) -> list:
    return get_admin_audits_scoped(resolve_commercial_scope(), limit)


def get_admin_audits_scoped(scope: CommercialScope, limit: int = 200) -> list:
    if postgres_utils.use_postgres():
        try:
            safe_limit = max(1, min(int(limit), _max_records()))
            postgres_utils.init_schema()
            with postgres_utils.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT audit_id, actor, action, target_type, target_id, metadata, created_at
                        FROM admin_audit_logs
                        WHERE tenant_id = %s AND (store_id = %s OR store_id IS NULL)
                        ORDER BY created_at DESC, id DESC
                        LIMIT %s
                        """,
                        (scope.tenant_id, scope.store_id, safe_limit),
                    )
                    return list(reversed(cur.fetchall()))
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_store_scope(scope):
        return []
    with _lock:
        rows = _read()
    try:
        safe_limit = max(1, min(int(limit), _max_records()))
    except Exception:
        safe_limit = 200
    return rows[-safe_limit:]
