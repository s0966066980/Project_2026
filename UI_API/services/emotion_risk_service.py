from utils.text_utils import normalize_emotion_label, to_traditional_lite


EMOTION_RISK_RULES = [
    {"range": "1-2", "level": "stable", "action": "不觸發介入，只保存觀察。"},
    {"range": "3-4", "level": "watch", "action": "持續觀察，可用低干擾提示。"},
    {"range": "5-6", "level": "assist", "action": "顯示操作、付款或推薦輔助。"},
    {"range": "7-8", "level": "urgent", "action": "縮短回覆、優先安撫，必要時通知店員。"},
    {"range": "9-10", "level": "critical", "action": "立即通知真人店員，停止推銷式推薦。"},
]

BASE_SCORE_BY_LABEL = {
    "未偵測到顧客": 2,
    "平靜": 1,
    "開心": 1,
    "疲憊": 3,
    "猶豫": 4,
    "困惑": 5,
    "焦躁": 7,
    "生氣": 9,
    "難過": 5,
    "驚訝": 4,
    "無法判斷": 3,
}

PAYMENT_TERMS = ["不能刷", "付款", "刷卡", "line pay", "悠遊卡", "支付"]
OPERATION_TERMS = ["不會", "不懂", "怎麼用", "看不懂", "怎麼點"]
COMPLAINT_TERMS = ["客訴", "投訴", "不爽", "爛", "太誇張", "找經理", "抱怨"]
URGENT_TERMS = ["趕時間", "快一點", "等很久", "太慢", "急"]


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(term or "").lower() in lowered for term in terms)


def _emotion_label(emotion_structured: dict | None) -> str:
    emotion = emotion_structured if isinstance(emotion_structured, dict) else {}
    label = normalize_emotion_label(str(emotion.get("emotion_label") or "").strip())
    if label:
        return label
    display = str(emotion.get("emotion_display") or "")
    label = normalize_emotion_label(display)
    return label or "無法判斷"


def _risk_level(score: int) -> str:
    if score <= 2:
        return "stable"
    if score <= 4:
        return "watch"
    if score <= 6:
        return "assist"
    if score <= 8:
        return "urgent"
    return "critical"


def calculate_emotion_risk(
    emotion_structured: dict | None = None,
    media_signals: dict | None = None,
    speech_text: str = "",
    person_check: dict | None = None,
) -> dict:
    emotion = emotion_structured if isinstance(emotion_structured, dict) else {}
    media = media_signals if isinstance(media_signals, dict) else {}
    person = person_check if isinstance(person_check, dict) else {}
    speech = to_traditional_lite(str(speech_text or emotion.get("speech_text") or ""))
    label = _emotion_label(emotion)
    distribution = emotion.get("emotion_distribution") if isinstance(emotion.get("emotion_distribution"), dict) else {}

    score = BASE_SCORE_BY_LABEL.get(label, 3)
    evidence = [f"emotion_label={label}", f"base_score={score}"]

    try:
        angry_pct = int(float(distribution.get("生氣", 0)))
        irritated_pct = int(float(distribution.get("焦躁", 0)))
        confused_pct = int(float(distribution.get("困惑", 0)))
        hesitant_pct = int(float(distribution.get("猶豫", 0)))
    except Exception:
        angry_pct = irritated_pct = confused_pct = hesitant_pct = 0

    if angry_pct >= 40:
        score += 2
        evidence.append("生氣分佈 >= 40%")
    if irritated_pct >= 45:
        score += 1
        evidence.append("焦躁分佈 >= 45%")
    if max(confused_pct, hesitant_pct) >= 55:
        score += 1
        evidence.append("困惑/猶豫分佈 >= 55%")

    if _contains_any(speech, COMPLAINT_TERMS):
        score += 2
        evidence.append("speech contains complaint risk")
    if _contains_any(speech, URGENT_TERMS):
        score += 2
        evidence.append("speech contains urgent or waiting terms")
    if _contains_any(speech, PAYMENT_TERMS + OPERATION_TERMS):
        score += 1
        evidence.append("speech contains payment or operation issue")

    if media.get("motion_level") == "active" and label in {"焦躁", "生氣", "困惑"}:
        score += 1
        evidence.append("active motion with negative emotion")
    if media.get("audio_silent") and not speech.strip() and label in {"無法判斷", "未偵測到顧客"}:
        score = min(score, 2)
        evidence.append("silent audio with low-confidence emotion caps score")
    if person.get("available") and person.get("person_detected") is False and not speech.strip():
        score = min(score, 2)
        evidence.append("no customer detected caps score")

    score = max(1, min(10, int(score)))
    return {
        "emotion_risk_score": score,
        "emotion_risk_score_scale": 10,
        "emotion_risk_level": _risk_level(score),
        "emotion_risk_rules": EMOTION_RISK_RULES,
        "emotion_risk_evidence": evidence,
    }
