"""推薦事件 repository。

推薦事件比一般互動事件更結構化，獨立保存方便後續統計：
曝光、點擊、加入購物車、成交、忽略。
"""
import json
import os
import threading

import config
from repositories import postgres_utils


RECOMMENDATION_EVENTS_PATH = os.path.join(config.LEARNING_DATA_DIR, "recommendation_events.json")
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


def _postgres_append_events(events: list[dict]) -> list[dict]:
    postgres_utils.init_schema()
    records = [dict(event or {}) for event in events if isinstance(event, dict) and _event_id(event)]
    if not records:
        return []
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            for event in records:
                cur.execute(
                    """
                    INSERT INTO recommendation_events (
                        event_id, recommendation_id, session_id, member_phone_masked,
                        is_member, event_type, surface, source, item_id, item_name,
                        category, rank, score, reasons, quantity, metadata, timestamp
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    """,
                    (
                        _event_id(event),
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
        conn.commit()
    return records


def _postgres_get_events(session_id: str = "", limit: int = 200) -> list:
    postgres_utils.init_schema()
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
                    WHERE session_id = %s
                    ORDER BY timestamp DESC, event_id DESC
                    LIMIT %s
                    """,
                    (str(session_id), safe_limit),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM recommendation_events
                    ORDER BY timestamp DESC, event_id DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
            rows = cur.fetchall()
    return list(reversed(rows))


def _postgres_clear_events() -> int:
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM recommendation_events")
            count = cur.rowcount
        conn.commit()
    return count


def append_recommendation_event(event: dict) -> dict:
    if postgres_utils.use_postgres():
        try:
            records = _postgres_append_events([event])
            return records[0] if records else dict(event or {})
        except Exception:
            pass
    rows = _read_list(RECOMMENDATION_EVENTS_PATH)
    record = dict(event or {})
    rows.append(record)
    _write_list(RECOMMENDATION_EVENTS_PATH, rows)
    return record


def append_recommendation_events(events: list[dict]) -> list[dict]:
    if not events:
        return []
    if postgres_utils.use_postgres():
        try:
            return _postgres_append_events(events)
        except Exception:
            pass
    rows = _read_list(RECOMMENDATION_EVENTS_PATH)
    records = [dict(event or {}) for event in events if isinstance(event, dict)]
    rows.extend(records)
    _write_list(RECOMMENDATION_EVENTS_PATH, rows)
    return records


def get_recommendation_events(session_id: str = "", limit: int = 200) -> list:
    if postgres_utils.use_postgres():
        try:
            return _postgres_get_events(session_id, limit)
        except Exception:
            pass
    rows = _read_list(RECOMMENDATION_EVENTS_PATH)
    if session_id:
        rows = [row for row in rows if str(row.get("session_id") or "") == str(session_id)]
    try:
        safe_limit = max(1, min(int(limit), MAX_RECORDS))
    except Exception:
        safe_limit = 200
    return rows[-safe_limit:]


def clear_recommendation_events() -> int:
    if postgres_utils.use_postgres():
        try:
            return _postgres_clear_events()
        except Exception:
            pass
    rows = _read_list(RECOMMENDATION_EVENTS_PATH)
    count = len(rows)
    _write_list(RECOMMENDATION_EVENTS_PATH, [])
    return count
