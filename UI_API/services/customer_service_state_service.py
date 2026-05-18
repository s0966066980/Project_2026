from utils.text_utils import to_traditional_lite


PAYMENT_TERMS = ["不能刷", "付款", "刷卡", "LINE Pay", "line pay", "悠遊卡"]
COUPON_TERMS = ["優惠券", "折扣碼", "掃碼", "QR", "qr"]
OPERATION_TERMS = ["不會", "不懂", "怎麼用", "看不懂", "怎麼點"]
COMPLAINT_TERMS = ["客訴", "投訴", "不爽", "爛", "太誇張", "找經理"]
URGENT_TERMS = ["趕時間", "快一點", "等很久", "太慢"]
WAITING_TERMS = ["趕時間", "快一點", "等很久", "太慢", "等待"]


def _safe_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _contains_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    for term in terms:
        haystack = lower if any("a" <= char.lower() <= "z" for char in term) else text
        if term.lower() in haystack:
            return True
    return False


def _emotion_label(emotion_structured: dict | None) -> str:
    emotion = _safe_dict(emotion_structured)
    label = str(emotion.get("emotion_label") or "").strip()
    if label:
        return label
    display = str(emotion.get("emotion_display") or "")
    for candidate in ["生氣", "焦躁", "困惑", "猶豫", "疲憊", "平靜", "無法判斷"]:
        if candidate in display:
            return candidate
    return ""


def infer_customer_service_state(
    user_text: str,
    emotion_structured: dict | None = None,
    media_signals: dict | None = None,
    person_check: dict | None = None,
    ui_context: dict | None = None,
    risk_result: dict | None = None,
) -> dict:
    text = to_traditional_lite(str(user_text or "")).strip()
    emotion_label = _emotion_label(emotion_structured)
    media = _safe_dict(media_signals)
    person = _safe_dict(person_check)
    ui = _safe_dict(ui_context)
    risk = _safe_dict(risk_result)
    evidence = []

    state = "normal_question"
    priority = "normal"
    needs_human_staff = False

    has_payment_issue = _contains_any(text, PAYMENT_TERMS)
    has_coupon_issue = _contains_any(text, COUPON_TERMS)
    has_operation_confusion = _contains_any(text, OPERATION_TERMS)
    has_complaint = _contains_any(text, COMPLAINT_TERMS)
    has_urgent = _contains_any(text, URGENT_TERMS)

    if has_payment_issue:
        state = "payment_issue"
        priority = "medium"
        evidence.append("user_text contains payment issue")
    if has_coupon_issue:
        state = "coupon_issue"
        priority = "medium"
        evidence.append("user_text contains coupon or QR issue")
    if has_operation_confusion:
        state = "operation_confusion"
        priority = "medium"
        evidence.append("user_text contains operation confusion")
    if has_urgent:
        state = "urgent_request"
        priority = "medium"
        evidence.append("user_text contains waiting or urgent request")
    if has_complaint:
        state = "complaint_risk"
        priority = "high"
        needs_human_staff = True
        evidence.append("user_text contains complaint risk")

    if emotion_label:
        evidence.append(f"emotion_label={emotion_label}")
    if emotion_label == "生氣":
        state = "angry_customer"
        priority = "high"
        needs_human_staff = True
        evidence.append("angry emotion requires human staff")
    elif emotion_label == "焦躁" and (has_payment_issue or has_urgent or _contains_any(text, WAITING_TERMS)):
        needs_human_staff = True
        if priority != "high":
            priority = "high"
        if state == "normal_question":
            state = "needs_human_staff"
        evidence.append("irritated emotion with payment or waiting issue")

    if not text and not emotion_label:
        state = "low_confidence"
        priority = "normal"
        evidence.append("insufficient speech and emotion evidence")
    elif state == "normal_question":
        if media.get("audio_silent") and person.get("person_detected") is not True:
            state = "low_confidence"
            evidence.append("audio silent and person not clearly detected")
        else:
            evidence.append("no high-risk customer service condition detected")

    page_id = ui.get("page_id")
    if page_id:
        evidence.append(f"page_id={page_id}")
    risk_score = risk.get("risk_score")
    if risk_score is not None:
        evidence.append(f"risk_score={risk_score}")

    return {
        "customer_service_state": state,
        "priority": priority,
        "needs_human_staff": needs_human_staff,
        "evidence": evidence,
    }
