"""推薦事件 repository。

推薦事件比一般互動事件更結構化，獨立保存方便後續統計：
曝光、點擊、加入購物車、成交、忽略。
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone

import config
from models.commercial_scope import (
    CommercialScope,
    CommercialScopeConflictError,
    is_legacy_store_scope,
)
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope

RECOMMENDATION_EVENTS_PATH = os.path.join(config.LEARNING_DATA_DIR, "recommendation_events.json")

# The operations overview computes the push funnel from these same rows, so a
# clear that took everything would blank the statistics an operator had just
# been reading. Thirty days keeps that window and removes what is behind it.
DEFAULT_CLEAR_RETAIN_DAYS = 30


def _clear_cutoff(retain_days: int) -> str:
    """The ISO instant before which events may be deleted."""

    return (datetime.now(timezone.utc) - timedelta(days=max(0, int(retain_days)))).isoformat()


MAX_RECORDS = 5000

_cache_lock = threading.Lock()
_write_lock = threading.Lock()
_cache: dict[str, tuple[float | None, list]] = {}


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
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        result = data if isinstance(data, list) else []
    except Exception:
        return []
    with _cache_lock:
        _cache[path] = (mtime, list(result))
    return list(result)


def _write_list(path: str, rows: list) -> list:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    trimmed = list(rows[-MAX_RECORDS:])
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with _write_lock:
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(trimmed, handle, ensure_ascii=False, indent=4)
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


def _jsonb(value, default):
    try:
        from psycopg.types.json import Jsonb
    except Exception as exc:
        raise postgres_utils.PostgresUnavailableError("psycopg Jsonb support is required") from exc
    return Jsonb(value if isinstance(value, type(default)) else default)


def _event_id(event: dict) -> str:
    return str(event.get("event_id") or event.get("id") or "").strip()


def _postgres_append_events(events: list[dict], scope: CommercialScope) -> list[dict]:
    records = [dict(event or {}) for event in events if isinstance(event, dict) and _event_id(event)]
    if not records:
        return []
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            for event in records:
                cur.execute(
                    """
                    INSERT INTO recommendation_events (
                        event_id, tenant_id, store_id, device_id,
                        recommendation_id, session_id, member_phone_masked,
                        is_member, event_type, surface, source, item_id, item_name,
                        category, rank, score, reasons, quantity, metadata, timestamp
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO UPDATE SET
                        recommendation_id = EXCLUDED.recommendation_id,
                        session_id = EXCLUDED.session_id,
                        member_phone_masked = EXCLUDED.member_phone_masked,
                        is_member = EXCLUDED.is_member,
                        event_type = EXCLUDED.event_type,
                        surface = EXCLUDED.surface,
                        source = EXCLUDED.source,
                        item_id = EXCLUDED.item_id,
                        item_name = EXCLUDED.item_name,
                        category = EXCLUDED.category,
                        rank = EXCLUDED.rank,
                        score = EXCLUDED.score,
                        reasons = EXCLUDED.reasons,
                        quantity = EXCLUDED.quantity,
                        metadata = EXCLUDED.metadata,
                        timestamp = EXCLUDED.timestamp
                    WHERE recommendation_events.tenant_id = EXCLUDED.tenant_id
                      AND recommendation_events.store_id = EXCLUDED.store_id
                      AND recommendation_events.device_id IS NOT DISTINCT FROM EXCLUDED.device_id
                    RETURNING event_id
                    """,
                    (
                        _event_id(event),
                        scope.tenant_id,
                        scope.store_id,
                        scope.device_id,
                        str(event.get("recommendation_id") or ""),
                        str(event.get("session_id") or ""),
                        str(event.get("member_phone_masked") or ""),
                        bool(event.get("is_member", False)),
                        str(event.get("event_type") or ""),
                        str(event.get("surface") or ""),
                        str(event.get("source") or ""),
                        str(event.get("item_id") or ""),
                        str(event.get("item_name") or ""),
                        str(event.get("category") or ""),
                        int(event.get("rank", 0) or 0),
                        int(event.get("score", 0) or 0),
                        _jsonb(event.get("reasons"), []),
                        int(event.get("quantity", 0) or 0),
                        _jsonb(event.get("metadata"), {}),
                        str(event.get("timestamp") or ""),
                    ),
                )
                if cur.fetchone() is None:
                    raise CommercialScopeConflictError(
                        "Recommendation event ID is already owned by another commercial scope"
                    )
        conn.commit()
    return records


def _postgres_get_events(scope: CommercialScope, session_id: str = "", limit: int = 200) -> list:
    try:
        safe_limit = max(1, min(int(limit), MAX_RECORDS))
    except Exception:
        safe_limit = 200
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            if session_id:
                cur.execute(
                    """
                    SELECT * FROM recommendation_events
                    WHERE tenant_id = %s AND store_id = %s AND session_id = %s
                    ORDER BY timestamp DESC, event_id DESC
                    LIMIT %s
                    """,
                    (scope.tenant_id, scope.store_id, str(session_id), safe_limit),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM recommendation_events
                    WHERE tenant_id = %s AND store_id = %s
                    ORDER BY timestamp DESC, event_id DESC
                    LIMIT %s
                    """,
                    (scope.tenant_id, scope.store_id, safe_limit),
                )
            rows = cur.fetchall()
    return list(reversed(rows))


def _postgres_clear_events(scope: CommercialScope, older_than_days: int) -> int:
    """Delete this store's events, optionally keeping a recent window.

    The cutoff compares against the `timestamp` column, which is TEXT holding
    an ISO-8601 instant — not a `timestamptz` named `created_at`. Interval
    arithmetic would not even parse here, so the boundary is computed in
    Python and compared lexicographically, exactly as the JSON branch does.
    """

    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            if older_than_days <= 0:
                cur.execute(
                    "DELETE FROM recommendation_events WHERE tenant_id = %s AND store_id = %s",
                    (scope.tenant_id, scope.store_id),
                )
            else:
                cur.execute(
                    """
                    DELETE FROM recommendation_events
                    WHERE tenant_id = %s AND store_id = %s AND "timestamp" < %s
                    """,
                    (scope.tenant_id, scope.store_id, _clear_cutoff(older_than_days)),
                )
            count = cur.rowcount
        conn.commit()
    return count


def append_recommendation_event(event: dict) -> dict:
    return append_recommendation_event_scoped(event, resolve_commercial_scope())


def append_recommendation_event_scoped(event: dict, scope: CommercialScope) -> dict:
    if postgres_utils.use_postgres():
        try:
            records = _postgres_append_events([event], scope)
            return records[0] if records else dict(event or {})
        except CommercialScopeConflictError:
            raise
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON recommendation storage only supports the configured legacy default scope")
    rows = _read_list(RECOMMENDATION_EVENTS_PATH)
    record = dict(event or {})
    rows.append(record)
    _write_list(RECOMMENDATION_EVENTS_PATH, rows)
    return record


def append_recommendation_events(events: list[dict]) -> list[dict]:
    return append_recommendation_events_scoped(events, resolve_commercial_scope())


def append_recommendation_events_scoped(events: list[dict], scope: CommercialScope) -> list[dict]:
    if not events:
        return []
    if postgres_utils.use_postgres():
        try:
            return _postgres_append_events(events, scope)
        except CommercialScopeConflictError:
            raise
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON recommendation storage only supports the configured legacy default scope")
    rows = _read_list(RECOMMENDATION_EVENTS_PATH)
    records = [dict(event or {}) for event in events if isinstance(event, dict)]
    rows.extend(records)
    _write_list(RECOMMENDATION_EVENTS_PATH, rows)
    return records


def get_recommendation_events(session_id: str = "", limit: int = 200) -> list:
    return get_recommendation_events_scoped(resolve_commercial_scope(), session_id, limit)


def get_recommendation_events_scoped(
    scope: CommercialScope,
    session_id: str = "",
    limit: int = 200,
) -> list:
    if postgres_utils.use_postgres():
        try:
            return _postgres_get_events(scope, session_id, limit)
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_store_scope(scope):
        return []
    rows = _read_list(RECOMMENDATION_EVENTS_PATH)
    if session_id:
        rows = [row for row in rows if str(row.get("session_id") or "") == str(session_id)]
    try:
        safe_limit = max(1, min(int(limit), MAX_RECORDS))
    except Exception:
        safe_limit = 200
    return rows[-safe_limit:]


def count_shown_scoped(
    scope: CommercialScope,
    *,
    since: str,
    excluded_sources: tuple[str, ...] = (),
) -> int:
    """Count recommendations the store actually put in front of a customer.

    Excluding by source in the query rather than in the caller keeps a placeholder
    from being counted and subtracted back out, which is where a reporting number
    quietly stops meaning what its label says (ADR-0054).
    """

    if not postgres_utils.use_postgres():
        return 0
    excluded = tuple(str(source).strip() for source in excluded_sources if str(source).strip())
    try:
        with postgres_utils.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS total FROM recommendation_events
                    WHERE tenant_id = %s AND store_id = %s
                      AND event_type = 'recommendation_shown'
                      AND timestamp >= %s
                      AND COALESCE(NULLIF(TRIM(source), ''), '') <> ''
                      AND NOT (source = ANY(%s))
                    """,
                    (scope.tenant_id, scope.store_id, str(since), list(excluded)),
                )
                row = cur.fetchone() or {}
        return int(row.get("total") or 0)
    except Exception as exc:
        postgres_utils.handle_postgres_failure(exc)
        return 0


def clear_recommendation_events(older_than_days: int = DEFAULT_CLEAR_RETAIN_DAYS) -> int:
    return clear_recommendation_events_scoped(resolve_commercial_scope(), older_than_days=older_than_days)


def clear_recommendation_events_scoped(
    scope: CommercialScope, *, older_than_days: int = DEFAULT_CLEAR_RETAIN_DAYS
) -> int:
    """Delete this store's recommendation events older than a cutoff.

    The cutoff exists because these rows are not only a log: the operations
    overview computes the push funnel from the same events, so clearing
    everything would blank the statistics an operator had just been reading.
    Thirty days keeps the recent window that feeds those numbers and removes
    the accumulation behind it.

    `older_than_days=0` still clears everything, for the operator who really
    means it — but that has to be asked for.
    """

    retain = max(0, int(older_than_days))
    if postgres_utils.use_postgres():
        try:
            return _postgres_clear_events(scope, retain)
        except Exception as exc:
            postgres_utils.handle_postgres_failure(exc)
    if not is_legacy_store_scope(scope):
        return 0
    rows = _read_list(RECOMMENDATION_EVENTS_PATH)
    if retain <= 0:
        _write_list(RECOMMENDATION_EVENTS_PATH, [])
        return len(rows)
    cutoff = _clear_cutoff(retain)
    kept = [row for row in rows if str(row.get("timestamp") or row.get("created_at") or "") >= cutoff]
    _write_list(RECOMMENDATION_EVENTS_PATH, kept)
    return len(rows) - len(kept)
