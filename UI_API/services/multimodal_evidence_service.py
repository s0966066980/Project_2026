def _safe_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value) -> list:
    return value if isinstance(value, list) else []


def _short_text(value, limit: int = 120) -> str:
    text = str(value or "").strip()
    return text[:limit]


def build_multimodal_evidence(
    emotion_structured: dict | None,
    person_check: dict | None,
    media_signals: dict | None,
    speech_text: str = "",
    risk_result: dict | None = None,
    ui_context: dict | None = None,
    interaction_context: str = "",
) -> dict:
    emotion = _safe_dict(emotion_structured)
    person = _safe_dict(person_check)
    media = _safe_dict(media_signals)
    risk = _safe_dict(risk_result)
    ui = _safe_dict(ui_context)

    return {
        "visual_evidence": {
            "person_detected": person.get("person_detected"),
            "person_hits": person.get("person_hits", person.get("face_hits")),
            "frames_checked": person.get("frames_checked"),
            "motion_level": media.get("motion_level"),
        },
        "audio_evidence": {
            "speech_text": _short_text(speech_text),
            "audio_silent": media.get("audio_silent"),
            "audio_mean_db": media.get("audio_mean_db"),
        },
        "emotion_evidence": {
            "emotion_label": emotion.get("emotion_label", ""),
            "emotion_display": emotion.get("emotion_display", ""),
            "emotion_evidence": emotion.get("emotion_evidence", ""),
            "emotion_distribution": _safe_dict(emotion.get("emotion_distribution")),
        },
        "pos_evidence": {
            "page_id": str(ui.get("page_id") or "unknown"),
            "risk_score": risk.get("risk_score"),
            "trigger_reasons": _safe_list(risk.get("trigger_reasons")),
            "interaction_context": _short_text(interaction_context, 1200),
        },
    }
