import json
import os
import re
import threading
import time
from datetime import datetime
from uuid import UUID, uuid4

import config
from models.commercial_scope import CommercialScope, is_legacy_store_scope
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope

_write_lock: dict[str, threading.Lock] = {}
_write_lock_guard = threading.Lock()


INTERACTION_EVENTS_PATH = os.path.join(config.LEARNING_DATA_DIR, "interaction_events.json")
INTERVENTION_LOGS_PATH = os.path.join(config.LEARNING_DATA_DIR, "intervention_logs.json")
MAX_RECORDS = 3000
SAFE_METADATA_KEYS = {
    "source",
    "reason",
    "action",
    "payment",
    "fulfillment",
    "from",
    "to",
    "expected",
    "expected_patent_category",
    "expected_patent_intervention_type",
    "legacy_alias",
    "scenario_id",
    "scenario_label",
    "speech_text",
    "category_switch_count",
    "cart_remove_count",
    "recommend_ignore_count",
}
SAFE_UI_CONTEXT_KEYS = {"page_id", "cart_count", "promotion_paused", "service_open"}

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float | None, list]] = {}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


def _read_list(path: str) -> list:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    with _cache_lock:
        cached = _cache.get(path)
        if cached and cached[0] == mtime:
            return list(cached[1])
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []
    with _cache_lock:
        _cache[path] = (mtime, list(result))
    return list(result)


def _get_file_lock(path: str) -> threading.Lock:
    with _write_lock_guard:
        if path not in _write_lock:
            _write_lock[path] = threading.Lock()
        return _write_lock[path]


def _write_list(path: str, rows: list) -> list:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    trimmed = list(rows[-MAX_RECORDS:])
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    file_lock = _get_file_lock(path)
    with file_lock:
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(trimmed, f, ensure_ascii=False, indent=4)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    with _cache_lock:
        _cache[path] = (mtime, list(trimmed))
    return trimmed


def _recent(rows: list, limit: int) -> list:
    try:
        safe_limit = max(1, min(int(limit), MAX_RECORDS))
    except Exception:
        safe_limit = 200
    return rows[-safe_limit:]


def _parse_event_ts(row: dict) -> float:
    raw = row.get("timestamp", "")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except Exception:
        return 0.0


def _as_number(value, default=0):
    try:
        return int(float(value or default))
    except Exception:
        return default


def _safe_button_id(value) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))
    return cleaned[:80]


def _safe_scalar(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value[:120]
    return None


def _safe_metadata(metadata: object) -> dict:
    if not isinstance(metadata, dict):
        return {}
    safe = {}
    for key in SAFE_METADATA_KEYS:
        if key not in metadata:
            continue
        value = _safe_scalar(metadata.get(key))
        if value is not None:
            safe[key] = value
    return safe


def _safe_ui_context(record: dict) -> dict:
    candidate = record.get("ui_context")
    raw_context: dict = candidate if isinstance(candidate, dict) else {}
    safe = {"page_id": str(raw_context.get("page_id") or record.get("page_id") or "unknown")}
    for key in SAFE_UI_CONTEXT_KEYS - {"page_id"}:
        if key not in raw_context:
            continue
        value = _safe_scalar(raw_context.get(key))
        if value is not None:
            safe[key] = value
    return safe


def _privacy_event_vector(record: dict) -> dict:
    if not config.get("PRIVACY_STORE_EVENT_VECTOR_ONLY", True):
        return record
    vector = {
        "session_id": str(record.get("session_id") or "unknown"),
        "page_id": str(record.get("page_id") or "unknown"),
        "event_type": str(record.get("event_type") or "unknown"),
        "button_id": _safe_button_id(record.get("button_id")),
        "dwell_time_sec": _as_number(record.get("dwell_time_sec")),
        "back_count": _as_number(record.get("back_count")),
        "invalid_touch_count": _as_number(record.get("invalid_touch_count")),
        "payment_fail_count": _as_number(record.get("payment_fail_count")),
        "cart_edit_count": _as_number(record.get("cart_edit_count")),
        "category_switch_count": _as_number(record.get("category_switch_count")),
        "cart_remove_count": _as_number(record.get("cart_remove_count")),
        "recommend_ignore_count": _as_number(record.get("recommend_ignore_count")),
        "idle_time_sec": _as_number(record.get("idle_time_sec")),
        "metadata": _safe_metadata(record.get("metadata")),
        "ui_context": _safe_ui_context(record),
    }
    event_id = str(record.get("event_id") or "").strip()
    if event_id:
        # The id is an opaque deduplication key, not customer content. Keep it
        # so the PostgreSQL adapter's scoped upsert can make replay idempotent.
        vector["event_id"] = event_id[:128]
    return vector


def _require_device_scope(scope: CommercialScope) -> UUID:
    if scope.device_id is None:
        raise ValueError("Interaction persistence requires a device-scoped context")
    return scope.device_id


def append_interaction_event(event: dict) -> dict:
    return append_interaction_event_scoped(event, resolve_commercial_scope())


def append_interaction_event_scoped(event: dict, scope: CommercialScope) -> dict:
    device_id = _require_device_scope(scope)
    record = _privacy_event_vector(dict(event or {}))
    session_id = str(record.get("session_id") or "unknown")
    ts_ms = _timestamp_ms()
    record.setdefault("timestamp", _now_iso())
    record.setdefault("event_id", f"evt_{session_id}_{ts_ms}")
    if postgres_utils.use_postgres():
        from psycopg.types.json import Jsonb

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO interaction_events (
                    id, tenant_id, store_id, device_id, event_id,
                    session_id, event_type, payload, occurred_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, store_id, device_id, event_id) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    occurred_at = EXCLUDED.occurred_at
                RETURNING event_id
                """,
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.store_id,
                    device_id,
                    str(record["event_id"]),
                    session_id,
                    str(record.get("event_type") or "unknown"),
                    Jsonb(record),
                    str(record["timestamp"]),
                ),
            )
            conn.commit()
        return record
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON interaction storage only supports the legacy Default Scope")
    rows = _read_list(INTERACTION_EVENTS_PATH)
    rows.append(record)
    _write_list(INTERACTION_EVENTS_PATH, rows)
    return record


def get_interaction_events(session_id: str = "", limit: int = 200) -> list:
    return get_interaction_events_scoped(resolve_commercial_scope(), session_id, limit)


def get_interaction_events_scoped(
    scope: CommercialScope,
    session_id: str = "",
    limit: int = 200,
) -> list:
    try:
        safe_limit = max(1, min(int(limit), MAX_RECORDS))
    except Exception:
        safe_limit = 200
    if postgres_utils.use_postgres():
        params: list = [scope.tenant_id, scope.store_id]
        device_filter = ""
        if scope.device_id is not None:
            device_filter = " AND device_id = %s"
            params.append(scope.device_id)
        session_filter = ""
        if session_id:
            session_filter = " AND session_id = %s"
            params.append(str(session_id))
        params.append(safe_limit)
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT payload FROM interaction_events
                WHERE tenant_id = %s AND store_id = %s
                {device_filter}{session_filter}
                ORDER BY occurred_at DESC, id DESC LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(row["payload"]) for row in cur.fetchall()]
        return list(reversed(rows))
    if not is_legacy_store_scope(scope):
        return []
    rows = _read_list(INTERACTION_EVENTS_PATH)
    if session_id:
        rows = [row for row in rows if str(row.get("session_id", "")) == str(session_id)]
    return _recent(rows, limit)


def get_recent_session_events(session_id: str, window_sec: int = 120) -> list:
    return get_recent_session_events_scoped(resolve_commercial_scope(), session_id, window_sec)


def get_recent_session_events_scoped(
    scope: CommercialScope,
    session_id: str,
    window_sec: int = 120,
) -> list:
    if not session_id:
        return []
    now = time.time()
    try:
        safe_window = max(1, int(window_sec))
    except Exception:
        safe_window = 120
    rows = get_interaction_events_scoped(scope, session_id, MAX_RECORDS)
    result = []
    for row in rows:
        ts = _parse_event_ts(row)
        if ts and now - ts <= safe_window:
            result.append(row)
    return result


def append_intervention_log(log: dict) -> dict:
    return append_intervention_log_scoped(log, resolve_commercial_scope())


def append_intervention_log_scoped(log: dict, scope: CommercialScope) -> dict:
    device_id = _require_device_scope(scope)
    record = dict(log or {})
    session_id = str(record.get("session_id") or "unknown")
    ts_ms = _timestamp_ms()
    record.setdefault("timestamp", _now_iso())
    record.setdefault("intervention_id", f"int_{session_id}_{ts_ms}")
    if postgres_utils.use_postgres():
        from psycopg.types.json import Jsonb

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO intervention_outcomes (
                    id, tenant_id, store_id, device_id, intervention_id,
                    session_id, payload, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, store_id, device_id, intervention_id) DO NOTHING
                RETURNING intervention_id
                """,
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.store_id,
                    device_id,
                    str(record["intervention_id"]),
                    session_id,
                    Jsonb(record),
                    str(record["timestamp"]),
                ),
            )
            if cur.fetchone() is None:
                raise ValueError("Intervention ID already exists in this device scope")
            conn.commit()
        return record
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON intervention storage only supports the legacy Default Scope")
    rows = _read_list(INTERVENTION_LOGS_PATH)
    rows.append(record)
    _write_list(INTERVENTION_LOGS_PATH, rows)
    return record


def update_intervention_result(intervention_id: str, result: dict) -> dict | None:
    return update_intervention_result_scoped(intervention_id, result, resolve_commercial_scope())


def update_intervention_result_scoped(
    intervention_id: str,
    result: dict,
    scope: CommercialScope,
) -> dict | None:
    if not intervention_id:
        return None
    device_id = _require_device_scope(scope)
    if postgres_utils.use_postgres():
        from psycopg.types.json import Jsonb

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM intervention_outcomes
                WHERE tenant_id = %s AND store_id = %s AND device_id = %s
                  AND intervention_id = %s
                FOR UPDATE
                """,
                (scope.tenant_id, scope.store_id, device_id, str(intervention_id)),
            )
            row = cur.fetchone()
            if row is None:
                return None
            updated = dict(row["payload"])
            updated["result"] = dict(result or {})
            updated["result_updated_at"] = _now_iso()
            cur.execute(
                """
                UPDATE intervention_outcomes SET payload = %s, updated_at = NOW()
                WHERE tenant_id = %s AND store_id = %s AND device_id = %s
                  AND intervention_id = %s
                """,
                (Jsonb(updated), scope.tenant_id, scope.store_id, device_id, str(intervention_id)),
            )
            conn.commit()
        return updated
    if not is_legacy_store_scope(scope):
        return None
    rows = _read_list(INTERVENTION_LOGS_PATH)
    json_updated: dict | None = None
    for row in rows:
        if str(row.get("intervention_id", "")) == str(intervention_id):
            row["result"] = dict(result or {})
            row["result_updated_at"] = _now_iso()
            json_updated = row
            break
    if json_updated:
        _write_list(INTERVENTION_LOGS_PATH, rows)
    return json_updated


def find_latest_open_intervention(session_id: str) -> dict | None:
    return find_latest_open_intervention_scoped(resolve_commercial_scope(), session_id)


def find_latest_open_intervention_scoped(
    scope: CommercialScope,
    session_id: str,
) -> dict | None:
    if not session_id:
        return None
    rows = get_intervention_logs_scoped(scope, session_id, MAX_RECORDS)
    for row in reversed(rows):
        if str(row.get("session_id", "")) != str(session_id):
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        if result.get("closed") is True:
            continue
        if "checkout_success" in result or "payment_success" in result:
            continue
        return dict(row)
    return None


def get_intervention_logs(session_id: str = "", limit: int = 200) -> list:
    return get_intervention_logs_scoped(resolve_commercial_scope(), session_id, limit)


def get_intervention_logs_scoped(
    scope: CommercialScope,
    session_id: str = "",
    limit: int = 200,
) -> list:
    try:
        safe_limit = max(1, min(int(limit), MAX_RECORDS))
    except Exception:
        safe_limit = 200
    if postgres_utils.use_postgres():
        params: list = [scope.tenant_id, scope.store_id]
        device_filter = ""
        if scope.device_id is not None:
            device_filter = " AND device_id = %s"
            params.append(scope.device_id)
        session_filter = ""
        if session_id:
            session_filter = " AND session_id = %s"
            params.append(str(session_id))
        params.append(safe_limit)
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT payload FROM intervention_outcomes
                WHERE tenant_id = %s AND store_id = %s
                {device_filter}{session_filter}
                ORDER BY created_at DESC, id DESC LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(row["payload"]) for row in cur.fetchall()]
        return list(reversed(rows))
    if not is_legacy_store_scope(scope):
        return []
    rows = _read_list(INTERVENTION_LOGS_PATH)
    if session_id:
        rows = [row for row in rows if str(row.get("session_id", "")) == str(session_id)]
    return _recent(rows, limit)


def clear_intervention_logs() -> int:
    return clear_intervention_logs_scoped(resolve_commercial_scope())


def clear_intervention_logs_scoped(scope: CommercialScope) -> int:
    if postgres_utils.use_postgres():
        params: list = [scope.tenant_id, scope.store_id]
        device_filter = ""
        if scope.device_id is not None:
            device_filter = " AND device_id = %s"
            params.append(scope.device_id)
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM intervention_outcomes WHERE tenant_id = %s AND store_id = %s{device_filter}",
                tuple(params),
            )
            count = int(cur.rowcount)
            conn.commit()
        return count
    if not is_legacy_store_scope(scope):
        return 0
    rows = _read_list(INTERVENTION_LOGS_PATH)
    count = len(rows)
    _write_list(INTERVENTION_LOGS_PATH, [])
    return count


def clear_interaction_events() -> int:
    return clear_interaction_events_scoped(resolve_commercial_scope())


def clear_interaction_events_scoped(scope: CommercialScope) -> int:
    if postgres_utils.use_postgres():
        params: list = [scope.tenant_id, scope.store_id]
        device_filter = ""
        if scope.device_id is not None:
            device_filter = " AND device_id = %s"
            params.append(scope.device_id)
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM interaction_events WHERE tenant_id = %s AND store_id = %s{device_filter}",
                tuple(params),
            )
            count = int(cur.rowcount)
            conn.commit()
        return count
    if not is_legacy_store_scope(scope):
        return 0
    rows = _read_list(INTERACTION_EVENTS_PATH)
    count = len(rows)
    _write_list(INTERACTION_EVENTS_PATH, [])
    return count
