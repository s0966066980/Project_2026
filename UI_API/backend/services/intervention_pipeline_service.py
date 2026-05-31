import asyncio

from repositories import interaction_event_repository
from realtime import event_bus
from services import barrier_state_service
from services import intervention_service
from services import scenario_service


async def run_intervention_pipeline(
    session_id: str,
    ui_context: dict,
    recent_events: list | None = None,
    speech_text: str = "",
    scenario_id: str | None = None,
    source: str = "unknown",
    publish: bool = True,
) -> dict:
    safe_session_id = str(session_id or "anonymous")
    safe_ui_context = ui_context if isinstance(ui_context, dict) else {}
    events = recent_events if isinstance(recent_events, list) else await asyncio.to_thread(
        interaction_event_repository.get_recent_session_events,
        safe_session_id,
    )
    speech = str(speech_text or "")
    normalized_scenario = scenario_service.normalize_scenario_id(scenario_id or "")

    barrier_result = barrier_state_service.infer_barrier_state(
        speech_text=speech,
        pos_events=events,
        ui_context=safe_ui_context,
    )
    barrier_scenario = scenario_service.infer_scenario_from_barrier_state(
        barrier_result.get("barrier_state", "")
    )
    if barrier_scenario in scenario_service.MAIN_SCENARIO_IDS:
        normalized_scenario = barrier_scenario
    if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
        scenario_service.attach_scenario_metadata(barrier_result, normalized_scenario)

    intervention = intervention_service.decide_intervention(barrier_result, safe_ui_context)
    if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
        scenario_service.attach_scenario_metadata(intervention, normalized_scenario)

    intervention_log = None
    if barrier_result.get("barrier_state") != "normal_operation":
        log_payload = intervention_service.build_intervention_log(
            safe_session_id, barrier_result, intervention, safe_ui_context,
        )
        log_payload["source"] = source
        if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
            scenario_service.attach_scenario_metadata(log_payload, normalized_scenario)
        log_payload["patent_category"] = barrier_result.get("patent_category")
        log_payload["patent_intervention_type"] = intervention.get("patent_intervention_type")
        intervention_log = await asyncio.to_thread(
            interaction_event_repository.append_intervention_log,
            log_payload,
        )

    result = {
        "barrier_result": barrier_result,
        "intervention": intervention,
        "intervention_log": intervention_log,
        "source": source,
    }
    if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
        scenario_service.attach_scenario_metadata(result, normalized_scenario)

    if publish and intervention.get("action") != "none":
        await event_bus.publish_intervention(safe_session_id, result)
    if publish and intervention.get("staff_notify"):
        await event_bus.publish_to_admin("staff_notify", {
            "session_id": safe_session_id,
            "reason": intervention.get("reason", ""),
            "barrier_state": barrier_result.get("barrier_state"),
            "patent_category": barrier_result.get("patent_category"),
            "action": intervention.get("action"),
            "patent_intervention_type": intervention.get("patent_intervention_type"),
            "source": source,
        })

    return result
