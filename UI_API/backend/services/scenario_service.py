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
