NUMERIC_FIELDS = {
    "dwell_time_sec": 0.0,
    "back_count": 0,
    "invalid_touch_count": 0,
    "payment_fail_count": 0,
    "category_switch_count": 0,
    "cart_remove_count": 0,
}


def _as_int(value, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except Exception:
        return default


def _as_float(value, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except Exception:
        return default


def normalize_interaction_event(payload: dict) -> dict:
    raw = payload or {}
    event = {
        "session_id": str(raw.get("session_id") or "anonymous"),
        "page_id": str(raw.get("page_id") or "unknown"),
        "event_type": str(raw.get("event_type") or "unknown"),
        "button_id": str(raw.get("button_id") or ""),
        "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
        "ui_context": raw.get("ui_context") if isinstance(raw.get("ui_context"), dict) else {},
    }
    raw_metadata = event["metadata"]
    for field, default in NUMERIC_FIELDS.items():
        value = raw.get(field)
        if value is None and isinstance(raw_metadata, dict):
            value = raw_metadata.get(field)
        if isinstance(default, float):
            event[field] = _as_float(value, default)
        else:
            event[field] = _as_int(value, default)
    return event
