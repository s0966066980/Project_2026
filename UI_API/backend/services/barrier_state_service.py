

BARRIER_STATES = {
    "normal_operation", "menu_hesitation", "operation_confusion",
    "payment_confusion", "impatience_detected",
    "service_needed", "potential_complaint", "low_confidence",
}

INTERVENTION_CATEGORY_MAP = {
    "menu_hesitation": "menu_confusion",
    "payment_confusion": "operation_difficulty",
    "operation_confusion": "operation_difficulty",
    "impatience_detected": "service_needed",
    "service_needed": "service_needed",
    "potential_complaint": "service_needed",
    "low_confidence": "menu_confusion",
    "normal_operation": "none",
}

INTERVENTION_CATEGORY_LABELS = {
    "menu_confusion": "困惑不知道吃什麼",
    "operation_difficulty": "不會操作機台",
    "service_needed": "需要客服協助",
    "none": "操作正常",
}

PATENT_CATEGORY_MAP = {
    "menu_hesitation": "decision_hesitation",
    "payment_confusion": "operation_failure",
    "operation_confusion": "operation_failure",
    "impatience_detected": "service_or_question",
    "service_needed": "service_or_question",
    "potential_complaint": "service_or_question",
    "low_confidence": "service_or_question",
    "normal_operation": "none",
}

PATENT_CATEGORY_LABELS = {
    "decision_hesitation": "困惑、無法決定餐點",
    "operation_failure": "操作失敗、不會點餐",
    "service_or_question": "詢問餐點、客服情況",
    "none": "正常操作",
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


def _max_field(pos_events: list | None, field: str) -> int:
    values = []
    for event in pos_events or []:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        try:
            values.append(int(float(event.get(field, metadata.get(field)) or 0)))
        except Exception:
            continue
    return max(values) if values else 0


def _latest_event_type(pos_events: list | None) -> str:
    for event in reversed(pos_events or []):
        if isinstance(event, dict) and event.get("event_type"):
            return str(event.get("event_type"))
    return ""


def _confidence_from(evidence_count: int) -> float:
    return round(min(0.95, 0.45 + evidence_count * 0.08), 2)


def _severity_from(evidence_count: int) -> float:
    return round(min(1.0, 0.25 + evidence_count * 0.08), 2)


def map_barrier_to_default_action(barrier_state: str) -> str:
    mapping = {
        "payment_confusion": "show_payment_tutorial",
        "operation_confusion": "show_operation_hint",
        "menu_hesitation": "recommend_popular_combo",
        "impatience_detected": "call_staff",
        "service_needed": "call_staff",
        "potential_complaint": "call_staff",
        "low_confidence": "ask_clarifying_question",
        "normal_operation": "none",
    }
    return mapping.get(barrier_state, "ask_clarifying_question")


def map_barrier_to_category(barrier_state: str) -> dict:
    key = INTERVENTION_CATEGORY_MAP.get(barrier_state, "menu_confusion")
    return {
        "intervention_category": key,
        "intervention_category_label": INTERVENTION_CATEGORY_LABELS.get(key, ""),
    }


def map_barrier_to_patent_category(barrier_state: str) -> dict:
    key = PATENT_CATEGORY_MAP.get(barrier_state, "service_or_question")
    return {
        "patent_category": key,
        "patent_category_label": PATENT_CATEGORY_LABELS.get(key, ""),
    }


def infer_barrier_state(
    speech_text: str = "",
    pos_events: list | None = None,
    ui_context: dict | None = None,
) -> dict:
    events = pos_events or []
    page_id = _latest_page(events, ui_context)
    speech = speech_text or ""
    evidence = []

    payment_fail_count = _max_field(events, "payment_fail_count")
    category_switch_count = _max_field(events, "category_switch_count")
    cart_remove_count = _max_field(events, "cart_remove_count")
    max_dwell_time_sec = _max_field(events, "dwell_time_sec")
    latest_event_type = _latest_event_type(events)

    barrier_state = "normal_operation"
    if _contains_any(speech, ["客訴", "投訴", "不爽", "太誇張", "我要找人", "經理", "爛"]):
        barrier_state = "potential_complaint"
        evidence.append("speech contains complaint intent")
    elif page_id == "payment_page" and payment_fail_count >= 1:
        barrier_state = "payment_confusion"
        evidence.extend(["page_id=payment_page", "payment_fail_count >= 1"])
    elif _contains_any(speech, ["不能刷", "付款", "刷卡", "line pay", "LINE Pay", "悠遊卡"]):
        barrier_state = "payment_confusion"
        evidence.append("speech contains payment issue")
    elif _contains_any(speech, ["不知道吃什麼", "推薦", "吃什麼", "選不出來", "猶豫"]):
        barrier_state = "menu_hesitation"
        evidence.append("speech contains menu hesitation")
    elif page_id == "menu_page" and (
        category_switch_count >= 4
        or cart_remove_count >= 2
        or latest_event_type in ("menu_page_dwell_timeout", "category_switch_repeat")
        or max_dwell_time_sec > 40
    ):
        barrier_state = "menu_hesitation"
        evidence.append("page_id=menu_page")
        if category_switch_count >= 4:
            evidence.append("category_switch_count >= 4")
        if cart_remove_count >= 2:
            evidence.append("cart_remove_count >= 2")
        if latest_event_type in ("menu_page_dwell_timeout", "category_switch_repeat"):
            evidence.append(f"event_type={latest_event_type}")
        if max_dwell_time_sec > 40:
            evidence.append("dwell_time_sec > 40")
    elif _contains_any(speech, ["不會", "不懂", "怎麼用", "看不懂", "怎麼點"]):
        barrier_state = "operation_confusion"
        evidence.append("speech contains operation confusion")
    elif _contains_any(speech, ["太慢", "等很久", "快一點", "趕時間"]):
        barrier_state = "impatience_detected"
        evidence.append("speech contains impatience")
    elif not events and not speech.strip():
        barrier_state = "low_confidence"
        evidence.append("insufficient context")

    if barrier_state != "normal_operation":
        if payment_fail_count >= 1 and "payment_fail_count >= 1" not in evidence:
            evidence.append("payment_fail_count >= 1")
        if page_id and page_id != "unknown" and f"page_id={page_id}" not in evidence:
            evidence.append(f"page_id={page_id}")

    confidence = _confidence_from(len(evidence))
    severity = _severity_from(len(evidence))
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
        "recommended_action": map_barrier_to_default_action(barrier_state),
        "payment_fail_count": payment_fail_count,
        "category_switch_count": category_switch_count,
        "cart_remove_count": cart_remove_count,
        **map_barrier_to_category(barrier_state),
        **map_barrier_to_patent_category(barrier_state),
    }
