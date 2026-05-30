import asyncio

from fastapi import APIRouter, Body

from repositories import interaction_event_repository
from services import interaction_event_service
from services import intervention_pipeline_service
from services import scenario_service


SCENARIOS = {
    "operation_difficulty": {
        "page_id": "menu_page",
        "event_type": "invalid_touch",
        "button_id": "demo_invalid_touch",
        "invalid_touch_count": 3,
        "dwell_time_sec": 35,
        "speech_text": "我不會操作，不知道怎麼點餐。",
        "metadata": {
            "source": "demo",
            "reason": "patent_operation_difficulty",
            "scenario_id": "operation_difficulty",
            "scenario_label": "點餐機操作困難",
            "speech_text": "我不會操作，不知道怎麼點餐。",
            "expected_patent_category": "operation_failure",
            "expected_patent_intervention_type": "operation_hint",
        },
    },
    "menu_hesitation": {
        "page_id": "menu_page",
        "event_type": "menu_page_dwell_timeout",
        "button_id": "demo_menu_hesitation",
        "dwell_time_sec": 45,
        "category_switch_count": 5,
        "speech_text": "我不知道要吃什麼，可以推薦嗎？",
        "metadata": {
            "source": "demo",
            "reason": "patent_menu_hesitation",
            "scenario_id": "menu_hesitation",
            "scenario_label": "餐點選擇猶豫",
            "category_switch_count": 5,
            "speech_text": "我不知道要吃什麼，可以推薦嗎？",
            "expected_patent_category": "decision_hesitation",
            "expected_patent_intervention_type": "recommendation",
        },
    },
    "payment_problem": {
        "page_id": "payment_page",
        "event_type": "payment_failed",
        "button_id": "demo_payment",
        "dwell_time_sec": 35,
        "payment_fail_count": 1,
        "speech_text": "付款一直失敗，請協助我完成付款。",
        "metadata": {
            "source": "demo",
            "payment": "failed",
            "scenario_id": "payment_problem",
            "scenario_label": "付款問題",
            "speech_text": "付款一直失敗，請協助我完成付款。",
            "expected_patent_category": "operation_failure",
            "expected_patent_intervention_type": "payment_tutorial",
        },
    },
    "human_service": {
        "page_id": "payment_page",
        "event_type": "payment_failed",
        "button_id": "demo_complaint",
        "payment_fail_count": 1,
        "dwell_time_sec": 38,
        "speech_text": "付款一直失敗，太誇張了，我要找經理客訴。",
        "metadata": {
            "source": "demo",
            "reason": "patent_human_service",
            "expected_patent_category": "service_or_question",
            "expected_patent_intervention_type": "human_service",
        },
    },
    "low_risk": {
        "page_id": "menu_page",
        "event_type": "menu_view",
        "button_id": "demo_menu_view",
        "dwell_time_sec": 5,
        "speech_text": "",
        "metadata": {
            "source": "demo",
            "reason": "patent_low_risk",
            "expected": "event_saved_only",
        },
    },
}

LEGACY_SCENARIO_ALIASES = {
    "operation_confusion": "operation_difficulty",
    "operation_confusion_explicit": "operation_difficulty",
    "invalid_touch": "operation_difficulty",
    "back_navigation": "operation_difficulty",
    "decision_hesitation": "menu_hesitation",
    "ask_recommendation": "menu_hesitation",
    "menu_confusion": "menu_hesitation",
    "payment_failed": "payment_problem",
    "payment_confusion": "payment_problem",
    "long_payment_dwell": "payment_problem",
    "coupon_error": "operation_difficulty",
    "customer_service_requested": "operation_difficulty",
    "complaint_risk": "operation_difficulty",
    "human_service": "operation_difficulty",
}


def _scenario_payload(payload: dict) -> tuple[dict, str, str, str]:
    requested = str((payload or {}).get("scenario") or "operation_difficulty")
    scenario = LEGACY_SCENARIO_ALIASES.get(requested) or scenario_service.normalize_scenario_id(requested)
    if scenario not in SCENARIOS:
        scenario = "operation_difficulty"
    base = dict(SCENARIOS.get(scenario) or SCENARIOS["operation_difficulty"])
    if requested != scenario:
        metadata = dict(base.get("metadata") or {})
        metadata["legacy_alias"] = requested
        base["metadata"] = metadata
    overrides = (payload or {}).get("event") if isinstance((payload or {}).get("event"), dict) else {}
    speech_text = str((payload or {}).get("speech_text") or base.pop("speech_text", ""))
    session_id = str((payload or {}).get("session_id") or overrides.get("session_id") or "pos_demo_001")
    event = {
        "session_id": session_id,
        "back_count": 0,
        "invalid_touch_count": 0,
        "payment_fail_count": 0,
        "coupon_error_count": 0,
        "cart_edit_count": 0,
        "category_switch_count": 0,
        "cart_remove_count": 0,
        "recommend_ignore_count": 0,
        "idle_time_sec": 0,
        **base,
        **overrides,
    }
    event.setdefault("ui_context", {
        "page_id": event.get("page_id"),
        "cart_count": 1,
        "promotion_paused": False,
        "service_open": False,
    })
    return event, speech_text, scenario, requested


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/demo", tags=["demo"])

    @router.post("/trigger_scenario")
    async def trigger_scenario(payload: dict = Body(default={})):
        event_payload, speech_text, scenario, requested = _scenario_payload(payload)
        event = interaction_event_service.normalize_interaction_event(event_payload)
        saved_event = await asyncio.to_thread(
            interaction_event_repository.append_interaction_event, event
        )
        session_id = str(saved_event.get("session_id") or "")
        recent_events = await asyncio.to_thread(
            interaction_event_repository.get_recent_session_events, session_id
        )
        ui_context = saved_event.get("ui_context") if isinstance(saved_event.get("ui_context"), dict) else {}
        risk_result = interaction_event_service.calculate_interaction_risk(recent_events, ui_context)
        response = {
            "status": "success",
            "scenario": scenario,
            "scenario_id": scenario if scenario != "low_risk" else "low_risk",
            "scenario_label": (
                scenario_service.get_scenario_definition(scenario).get("label")
                or ("低風險正常操作" if scenario == "low_risk" else "")
            ),
            "requested_scenario": requested,
            "event": saved_event,
            "risk_result": risk_result,
            "barrier_result": None,
            "intervention": None,
            "intervention_log": None,
        }

        if not risk_result.get("triggered"):
            return response

        pipeline_result = await intervention_pipeline_service.run_intervention_pipeline(
            session_id=session_id,
            ui_context=ui_context,
            risk_result=risk_result,
            recent_events=recent_events,
            speech_text=speech_text,
            scenario_id=scenario if scenario != "low_risk" else None,
            source="demo_trigger_scenario",
        )

        response.update({
            "scenario_id": pipeline_result.get("scenario_id", response["scenario_id"]),
            "scenario_label": pipeline_result.get("scenario_label", response["scenario_label"]),
            "barrier_result": pipeline_result.get("barrier_result"),
            "intervention": pipeline_result.get("intervention"),
            "intervention_log": pipeline_result.get("intervention_log"),
            "multimodal_evidence": pipeline_result.get("multimodal_evidence"),
            "source": pipeline_result.get("source"),
        })
        return response

    return router
