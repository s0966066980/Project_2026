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
        "ui_context": raw.get("ui_context") if isinstance(raw.get("ui_context"), dict) else {},
    }
    for field, default in NUMERIC_FIELDS.items():
        if isinstance(default, float):
            event[field] = _as_float(raw.get(field), default)
        else:
            event[field] = _as_int(raw.get(field), default)
    return event


def _max_field(events: list, field: str):
    values = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        values.append(_as_float(event.get(field)) if field.endswith("_sec") else _as_int(event.get(field)))
    return max(values) if values else 0


def _latest_page_id(events: list, ui_context: dict | None):
    context_page = str((ui_context or {}).get("page_id") or "")
    if context_page:
        return context_page
    for event in reversed(events or []):
        if isinstance(event, dict) and event.get("page_id"):
            return str(event.get("page_id"))
    return "unknown"


def _event_score(event: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    event_type = str(event.get("event_type") or "")

    if event_type == "payment_failed":
        score += 3
        reasons.append("event_type=payment_failed")
    elif event_type == "coupon_error":
        score += 2
        reasons.append("event_type=coupon_error")
    elif event_type == "invalid_touch":
        score += 1
        reasons.append("event_type=invalid_touch")
    elif event_type == "checkout_error":
        score += 3
        reasons.append("event_type=checkout_error")
    elif event_type == "voice_order_failed":
        score += 1
        reasons.append("event_type=voice_order_failed")
    elif event_type == "customer_service_failed":
        score += 1
        reasons.append("event_type=customer_service_failed")

    return score, reasons


def calculate_interaction_risk(events: list, ui_context: dict | None = None) -> dict:
    safe_events = [event for event in (events if isinstance(events, list) else []) if isinstance(event, dict)]
    threshold = _as_int(config.get("INTERACTION_TRIGGER_THRESHOLD", 5), 5)
    total_score = 0
    reasons = []
    seen = set()

    def add_reason(reason: str):
        if reason not in seen:
            seen.add(reason)
            reasons.append(reason)

    for event in safe_events:
        score, event_reasons = _event_score(event)
        total_score += score
        for reason in event_reasons:
            add_reason(reason)

    max_payment_fail_count = _max_field(safe_events, "payment_fail_count")
    max_coupon_error_count = _max_field(safe_events, "coupon_error_count")
    max_back_count = _max_field(safe_events, "back_count")
    max_invalid_touch_count = _max_field(safe_events, "invalid_touch_count")
    max_dwell_time_sec = _max_field(safe_events, "dwell_time_sec")
    max_idle_time_sec = _max_field(safe_events, "idle_time_sec")
    latest_page_id = _latest_page_id(safe_events, ui_context)

    if max_payment_fail_count >= 1:
        total_score += 3
        add_reason("max_payment_fail_count >= 1")
    if max_coupon_error_count >= 1:
        total_score += 2
        add_reason("max_coupon_error_count >= 1")
    if max_back_count >= 2:
        total_score += 2
        add_reason("max_back_count >= 2")
    if max_invalid_touch_count >= 3:
        total_score += 1
        add_reason("max_invalid_touch_count >= 3")
    if max_dwell_time_sec > 30:
        total_score += 2
        add_reason("max_dwell_time_sec > 30")
    if max_idle_time_sec > 20:
        total_score += 1
        add_reason("max_idle_time_sec > 20")

    if latest_page_id == "payment_page" and max_dwell_time_sec > 25:
        total_score += 2
        add_reason("latest_page_id=payment_page and max_dwell_time_sec > 25")
    if latest_page_id == "checkout_page" and max_back_count >= 1:
        total_score += 1
        add_reason("latest_page_id=checkout_page and max_back_count >= 1")
    if latest_page_id == "menu_page" and max_invalid_touch_count >= 3 and max_dwell_time_sec > 30:
        total_score += 1
        add_reason("latest_page_id=menu_page and max_invalid_touch_count >= 3 and max_dwell_time_sec > 30")

    # 量化 0-10。0=無風險、1-3 低、4-6 中、7-10 高。原始累計分數保留在 risk_score_raw。
    risk_score = min(10, max(0, int(total_score)))
    if risk_score == 0:
        risk_level = "none"
    elif risk_score <= 3:
        risk_level = "low"
    elif risk_score <= 6:
        risk_level = "medium"
    else:
        risk_level = "high"

    risk_result = {
        "risk_score": risk_score,
        "risk_score_raw": total_score,
        "risk_score_scale": 10,
        "risk_level": risk_level,
        "triggered": risk_score >= threshold,
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
        f"互動障礙風險分數：{risk_result.get('risk_score', 0)}/{risk_result.get('risk_score_scale', 10)}（{risk_result.get('risk_level', 'none')}）",
        f"觸發門檻：{risk_result.get('threshold', 5)}/{risk_result.get('risk_score_scale', 10)}",
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
