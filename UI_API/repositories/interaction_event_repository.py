import json
import os
import time
from datetime import datetime

import config


INTERACTION_EVENTS_PATH = os.path.join(config.LEARNING_DATA_DIR, "interaction_events.json")
INTERVENTION_LOGS_PATH = os.path.join(config.LEARNING_DATA_DIR, "intervention_logs.json")
MAX_RECORDS = 3000


def _now_iso() -> str:
    return datetime.now().isoformat()


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


def _read_list(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _write_list(path: str, rows: list) -> list:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows[-MAX_RECORDS:], f, ensure_ascii=False, indent=4)
    return rows[-MAX_RECORDS:]


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


def _privacy_event_vector(record: dict) -> dict:
    if not config.get("PRIVACY_STORE_EVENT_VECTOR_ONLY", True):
        return record
    return {
        "session_id": str(record.get("session_id") or "unknown"),
        "page_id": str(record.get("page_id") or "unknown"),
        "event_type": str(record.get("event_type") or "unknown"),
        "button_id": "",
        "dwell_time_sec": _as_number(record.get("dwell_time_sec")),
        "back_count": _as_number(record.get("back_count")),
        "invalid_touch_count": _as_number(record.get("invalid_touch_count")),
        "payment_fail_count": _as_number(record.get("payment_fail_count")),
        "coupon_error_count": _as_number(record.get("coupon_error_count")),
        "cart_edit_count": _as_number(record.get("cart_edit_count")),
        "idle_time_sec": _as_number(record.get("idle_time_sec")),
        "metadata": {},
        "ui_context": {
            "page_id": str((record.get("ui_context") or {}).get("page_id") or record.get("page_id") or "unknown")
        },
    }


def append_interaction_event(event: dict) -> dict:
    rows = _read_list(INTERACTION_EVENTS_PATH)
    record = _privacy_event_vector(dict(event or {}))
    session_id = str(record.get("session_id") or "unknown")
    ts_ms = _timestamp_ms()
    record.setdefault("timestamp", _now_iso())
    record.setdefault("event_id", f"evt_{session_id}_{ts_ms}")
    rows.append(record)
    _write_list(INTERACTION_EVENTS_PATH, rows)
    return record


def get_interaction_events(session_id: str = "", limit: int = 200) -> list:
    rows = _read_list(INTERACTION_EVENTS_PATH)
    if session_id:
        rows = [row for row in rows if str(row.get("session_id", "")) == str(session_id)]
    return _recent(rows, limit)


def get_recent_session_events(session_id: str, window_sec: int = 120) -> list:
    if not session_id:
        return []
    now = time.time()
    try:
        safe_window = max(1, int(window_sec))
    except Exception:
        safe_window = 120
    rows = get_interaction_events(session_id, MAX_RECORDS)
    return [
        row for row in rows
        if _parse_event_ts(row) and now - _parse_event_ts(row) <= safe_window
    ]


def append_intervention_log(log: dict) -> dict:
    rows = _read_list(INTERVENTION_LOGS_PATH)
    record = dict(log or {})
    session_id = str(record.get("session_id") or "unknown")
    ts_ms = _timestamp_ms()
    record.setdefault("timestamp", _now_iso())
    record.setdefault("intervention_id", f"int_{session_id}_{ts_ms}")
    rows.append(record)
    _write_list(INTERVENTION_LOGS_PATH, rows)
    return record


def update_intervention_result(intervention_id: str, result: dict) -> dict | None:
    if not intervention_id:
        return None
    rows = _read_list(INTERVENTION_LOGS_PATH)
    updated = None
    for row in rows:
        if str(row.get("intervention_id", "")) == str(intervention_id):
            row["result"] = dict(result or {})
            row["result_updated_at"] = _now_iso()
            updated = row
            break
    if updated:
        _write_list(INTERVENTION_LOGS_PATH, rows)
    return updated


def find_latest_open_intervention(session_id: str) -> dict | None:
    if not session_id:
        return None
    rows = _read_list(INTERVENTION_LOGS_PATH)
    for row in reversed(rows):
        if str(row.get("session_id", "")) != str(session_id):
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        if result.get("closed") is True:
            continue
        if "checkout_success" in result or "payment_success" in result:
            continue
        return row
    return None


def get_intervention_logs(session_id: str = "", limit: int = 200) -> list:
    rows = _read_list(INTERVENTION_LOGS_PATH)
    if session_id:
        rows = [row for row in rows if str(row.get("session_id", "")) == str(session_id)]
    return _recent(rows, limit)
