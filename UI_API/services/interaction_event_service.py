import config


NUMERIC_FIELDS = {
    "dwell_time_sec": 0.0,
    "back_count": 0,
    "invalid_touch_count": 0,
    "payment_fail_count": 0,
    "coupon_error_count": 0,
    "cart_edit_count": 0,
    "idle_time_sec": 0.0,
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
    }
    for field, default in NUMERIC_FIELDS.items():
        if isinstance(default, float):
            event[field] = _as_float(raw.get(field), default)
        else:
            event[field] = _as_int(raw.get(field), default)
    return event


def _event_score(event: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    event_type = str(event.get("event_type") or "")
    page_id = str(event.get("page_id") or "")

    payment_fail_count = _as_int(event.get("payment_fail_count"))
    coupon_error_count = _as_int(event.get("coupon_error_count"))
    back_count = _as_int(event.get("back_count"))
    invalid_touch_count = _as_int(event.get("invalid_touch_count"))
    dwell_time_sec = _as_float(event.get("dwell_time_sec"))
    idle_time_sec = _as_float(event.get("idle_time_sec"))

    if payment_fail_count >= 1:
        score += 3
        reasons.append("payment_fail_count >= 1")
    if coupon_error_count >= 1:
        score += 2
        reasons.append("coupon_error_count >= 1")
    if back_count >= 2:
        score += 2
        reasons.append("back_count >= 2")
    if invalid_touch_count >= 3:
        score += 1
        reasons.append("invalid_touch_count >= 3")
    if dwell_time_sec > 30:
        score += 2
        reasons.append("dwell_time_sec > 30")
    if idle_time_sec > 20:
        score += 1
        reasons.append("idle_time_sec > 20")

    if event_type == "payment_failed":
        score += 3
        reasons.append("event_type=payment_failed")
    elif event_type == "coupon_error":
        score += 2
        reasons.append("event_type=coupon_error")
    elif event_type == "invalid_touch":
        score += 1
        reasons.append("event_type=invalid_touch")

    if page_id == "payment_page" and dwell_time_sec > 25:
        score += 2
        reasons.append("payment_page dwell_time_sec > 25")
    if page_id == "checkout_page" and back_count >= 1:
        score += 1
        reasons.append("checkout_page back_count >= 1")

    return score, reasons


def calculate_interaction_risk(events: list, ui_context: dict | None = None) -> dict:
    safe_events = events if isinstance(events, list) else []
    threshold = _as_int(config.get("INTERACTION_TRIGGER_THRESHOLD", 5), 5)
    total_score = 0
    reasons = []
    seen = set()

    for event in safe_events:
        if not isinstance(event, dict):
            continue
        score, event_reasons = _event_score(event)
        total_score += score
        for reason in event_reasons:
            if reason not in seen:
                seen.add(reason)
                reasons.append(reason)

    risk_result = {
        "risk_score": total_score,
        "triggered": total_score >= threshold,
        "threshold": threshold,
        "trigger_reasons": reasons,
        "event_count": len(safe_events),
        "ui_context": ui_context or {},
    }
    return risk_result


def build_interaction_context(events: list, risk_result: dict) -> str:
    safe_events = [event for event in (events or []) if isinstance(event, dict)]
    recent = safe_events[-8:]
    lines = [
        "【POS 操作事件風險摘要】",
        f"互動障礙風險分數：{risk_result.get('risk_score', 0)}",
        f"觸發門檻：{risk_result.get('threshold', 5)}",
        f"是否觸發多模態分析：{'是' if risk_result.get('triggered') else '否'}",
        "觸發原因：" + ("、".join(risk_result.get("trigger_reasons") or []) or "無"),
        "最近事件：",
    ]
    for event in recent:
        lines.append(
            "- "
            f"頁面={event.get('page_id', 'unknown')}，"
            f"事件={event.get('event_type', 'unknown')}，"
            f"按鈕={event.get('button_id', '') or '無'}，"
            f"停留={event.get('dwell_time_sec', 0)}秒，"
            f"返回={event.get('back_count', 0)}次，"
            f"付款失敗={event.get('payment_fail_count', 0)}次，"
            f"優惠券錯誤={event.get('coupon_error_count', 0)}次"
        )
    return "\n".join(lines)
