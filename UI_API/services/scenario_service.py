SCENARIO_DEFINITIONS = {
    "operation_difficulty": {
        "label": "點餐機操作困難",
        "legacy_aliases": [
            "operation_confusion",
            "operation_confusion_explicit",
            "invalid_touch",
            "back_navigation",
        ],
        "barrier_states": ["operation_confusion"],
        "patent_category": "operation_failure",
        "default_intervention_type": "operation_hint",
        "default_action": "show_operation_hint",
        "success_metrics": ["next_valid_action", "cart_add", "checkout_success"],
    },
    "menu_hesitation": {
        "label": "餐點選擇猶豫",
        "legacy_aliases": [
            "decision_hesitation",
            "ask_recommendation",
            "menu_confusion",
        ],
        "barrier_states": ["menu_hesitation"],
        "patent_category": "decision_hesitation",
        "default_intervention_type": "recommendation",
        "default_action": "recommend_popular_combo",
        "success_metrics": ["recommend_click", "cart_add", "checkout_success"],
    },
    "payment_problem": {
        "label": "付款問題",
        "legacy_aliases": [
            "payment_failed",
            "long_payment_dwell",
            "payment_confusion",
        ],
        "barrier_states": ["payment_confusion"],
        "patent_category": "operation_failure",
        "default_intervention_type": "payment_tutorial",
        "default_action": "show_payment_tutorial",
        "success_metrics": [
            "payment_retry",
            "payment_success",
            "counter_payment",
            "checkout_success",
        ],
    },
}

MAIN_SCENARIO_IDS = tuple(SCENARIO_DEFINITIONS)

_ALIAS_TO_SCENARIO = {
    alias: scenario_id
    for scenario_id, definition in SCENARIO_DEFINITIONS.items()
    for alias in definition.get("legacy_aliases", [])
}

_BARRIER_TO_SCENARIO = {
    barrier_state: scenario_id
    for scenario_id, definition in SCENARIO_DEFINITIONS.items()
    for barrier_state in definition.get("barrier_states", [])
}


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(keyword or "").lower() in lowered for keyword in keywords)


def _as_int(value, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except Exception:
        return default


def _metadata(event: dict) -> dict:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    return metadata


def _event_value(event: dict, key: str, default=None):
    if key in event:
        return event.get(key)
    return _metadata(event).get(key, default)


def normalize_scenario_id(raw: str) -> str:
    scenario_id = str(raw or "").strip()
    if not scenario_id:
        return ""
    if scenario_id in MAIN_SCENARIO_IDS:
        return scenario_id
    return _ALIAS_TO_SCENARIO.get(scenario_id, scenario_id)


def infer_scenario_from_barrier_state(barrier_state: str) -> str:
    return _BARRIER_TO_SCENARIO.get(str(barrier_state or ""), "")


def infer_scenario_from_event(event: dict, risk_result: dict | None = None) -> str:
    if not isinstance(event, dict):
        return ""

    page_id = str(_event_value(event, "page_id", "") or "")
    event_type = str(_event_value(event, "event_type", "") or "")
    metadata = _metadata(event)
    reason = str(metadata.get("reason") or "")
    speech_text = " ".join([
        str(event.get("speech_text") or ""),
        str(metadata.get("speech_text") or ""),
        str(metadata.get("speech_hint") or ""),
    ]).strip()

    if page_id == "payment_page" or event_type == "payment_failed":
        return "payment_problem"

    if (
        _contains_any(reason, ["hesitation", "recommend", "猶豫", "推薦"])
        or _contains_any(event_type, [
            "menu_page_dwell_timeout",
            "category_switch_repeat",
            "recommendation_ignored",
        ])
    ):
        return "menu_hesitation"

    if (
        _as_int(_event_value(event, "invalid_touch_count")) >= 3
        or _as_int(_event_value(event, "back_count")) >= 2
        or _contains_any(speech_text, ["不會", "怎麼點", "不懂"])
    ):
        return "operation_difficulty"

    if page_id == "menu_page" and (
        _as_int(_event_value(event, "category_switch_count")) >= 4
        or _as_int(_event_value(event, "cart_remove_count")) >= 2
        or _as_int(_event_value(event, "recommend_ignore_count")) >= 1
        or _contains_any(speech_text, ["不知道吃什麼", "推薦", "吃什麼", "選不出來", "猶豫"])
    ):
        return "menu_hesitation"

    risk = risk_result if isinstance(risk_result, dict) else {}
    for reason_text in risk.get("trigger_reasons") or []:
        reason_lower = str(reason_text or "").lower()
        if any(term in reason_lower for term in ["category_switch", "cart_remove", "menu_page"]):
            return "menu_hesitation"
        if any(term in reason_lower for term in ["payment", "付款"]):
            return "payment_problem"
        if any(term in reason_lower for term in ["invalid_touch", "back_count"]):
            return "operation_difficulty"

    return infer_scenario_from_barrier_state(str(risk.get("barrier_state") or ""))


def get_scenario_definition(scenario_id: str) -> dict:
    normalized = normalize_scenario_id(scenario_id)
    definition = SCENARIO_DEFINITIONS.get(normalized)
    return dict(definition) if isinstance(definition, dict) else {}


def attach_scenario_metadata(payload: dict, scenario_id: str | None = None) -> dict:
    if not isinstance(payload, dict):
        payload = {}
    normalized = normalize_scenario_id(scenario_id or payload.get("scenario_id") or "")
    definition = get_scenario_definition(normalized)
    if not definition:
        return payload
    payload["scenario_id"] = normalized
    payload["scenario_label"] = definition.get("label", "")
    payload["scenario_definition"] = definition
    return payload
