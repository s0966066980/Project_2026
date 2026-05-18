from services import interaction_event_service


BARRIER_STATES = {
    "normal_operation",
    "menu_hesitation",
    "operation_confusion",
    "payment_confusion",
    "coupon_confusion",
    "impatience_detected",
    "service_needed",
    "potential_complaint",
    "low_confidence",
}


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _latest_page(pos_events: list | None, ui_context: dict | None) -> str:
    context_page = str((ui_context or {}).get("page_id") or "")
    if context_page:
        return context_page
    for event in reversed(pos_events or []):
        if isinstance(event, dict) and event.get("page_id"):
            return str(event.get("page_id"))
    return "unknown"


def _sum_field(pos_events: list | None, field: str) -> int:
    total = 0
    for event in pos_events or []:
        if not isinstance(event, dict):
            continue
        try:
            total += int(float(event.get(field) or 0))
        except Exception:
            continue
    return total


def _confidence_from(score: int, evidence_count: int) -> float:
    return round(min(0.95, 0.45 + score * 0.04 + evidence_count * 0.06), 2)


def _severity_from(score: int, evidence_count: int) -> float:
    return round(min(1.0, 0.25 + score * 0.07 + evidence_count * 0.05), 2)


def map_barrier_to_default_action(barrier_state: str, severity: float) -> str:
    mapping = {
        "payment_confusion": "show_payment_tutorial",
        "coupon_confusion": "show_coupon_guide",
        "operation_confusion": "show_operation_hint",
        "menu_hesitation": "recommend_popular_combo",
        "impatience_detected": "call_staff_or_fast_mode",
        "service_needed": "call_staff",
        "potential_complaint": "call_staff",
        "low_confidence": "ask_clarifying_question",
        "normal_operation": "none",
    }
    return mapping.get(barrier_state, "ask_clarifying_question")


def infer_barrier_state(
    emotion_structured: dict | None,
    speech_text: str = "",
    pos_events: list | None = None,
    ui_context: dict | None = None,
    media_signals: dict | None = None,
    risk_result: dict | None = None,
) -> dict:
    events = pos_events or []
    risk = risk_result or interaction_event_service.calculate_interaction_risk(events, ui_context)
    risk_score = int(risk.get("risk_score") or 0)
    page_id = _latest_page(events, ui_context)
    speech = speech_text or ""
    emotion = emotion_structured or {}
    emotion_label = str(emotion.get("emotion_label") or "")
    evidence = []

    payment_fail_count = _sum_field(events, "payment_fail_count")
    coupon_error_count = _sum_field(events, "coupon_error_count")

    barrier_state = "normal_operation"
    if _contains_any(speech, ["客訴", "投訴", "不爽", "太誇張", "我要找人", "經理", "爛"]):
        barrier_state = "potential_complaint"
        evidence.append("speech contains complaint intent")
    elif page_id == "payment_page" and (risk_score >= 5 or payment_fail_count >= 1):
        barrier_state = "payment_confusion"
        evidence.extend(["page_id=payment_page", "payment risk triggered"])
    elif _contains_any(speech, ["不能刷", "付款", "刷卡", "line pay", "LINE Pay", "悠遊卡"]) and risk_score >= 1:
        barrier_state = "payment_confusion"
        evidence.append("speech contains payment issue")
    elif _contains_any(speech, ["優惠券", "折扣碼", "掃碼", "qr", "QR"]) and coupon_error_count >= 1:
        barrier_state = "coupon_confusion"
        evidence.extend(["coupon_error_count >= 1", "speech contains coupon issue"])
    elif _contains_any(speech, ["不會", "不懂", "怎麼用", "看不懂", "怎麼點"]):
        barrier_state = "operation_confusion"
        evidence.append("speech contains operation confusion")
    elif _contains_any(speech, ["太慢", "等很久", "快一點", "趕時間"]):
        barrier_state = "impatience_detected"
        evidence.append("speech contains impatience")
    elif emotion_label == "生氣" and risk_score >= 5:
        barrier_state = "service_needed" if risk_score >= 8 else "potential_complaint"
        evidence.append(f"emotion_label={emotion_label}")
    elif emotion_label == "焦躁" and risk_score >= 5:
        barrier_state = "service_needed" if risk_score >= 8 else "impatience_detected"
        evidence.append(f"emotion_label={emotion_label}")
    elif emotion_label == "猶豫" and page_id == "menu_page":
        barrier_state = "menu_hesitation"
        evidence.extend(["emotion_label=猶豫", "page_id=menu_page"])
    elif risk_score >= 5 and page_id == "coupon_page":
        barrier_state = "coupon_confusion"
        evidence.extend(["risk_score >= threshold", "page_id=coupon_page"])
    elif risk_score >= 5:
        barrier_state = "operation_confusion"
        evidence.append("risk_score >= threshold")
    elif not events and not speech.strip() and not emotion:
        barrier_state = "low_confidence"
        evidence.append("insufficient multimodal context")

    if payment_fail_count >= 1 and "payment_fail_count >= 1" not in evidence:
        evidence.append("payment_fail_count >= 1")
    if page_id and f"page_id={page_id}" not in evidence:
        evidence.append(f"page_id={page_id}")
    if emotion_label and f"emotion_label={emotion_label}" not in evidence:
        evidence.append(f"emotion_label={emotion_label}")
    for reason in risk.get("trigger_reasons") or []:
        if reason not in evidence:
            evidence.append(reason)

    confidence = _confidence_from(risk_score, len(evidence))
    severity = _severity_from(risk_score, len(evidence))
    if barrier_state == "normal_operation":
        confidence = max(0.55, min(confidence, 0.75))
        severity = min(severity, 0.25)
    if barrier_state == "low_confidence":
        confidence = 0.35
        severity = 0.2

    return {
        "barrier_state": barrier_state,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "risk_score": risk_score,
        "recommended_action": map_barrier_to_default_action(barrier_state, severity),
        "emotion_label": emotion_label,
        "media_signals": media_signals or {},
    }
