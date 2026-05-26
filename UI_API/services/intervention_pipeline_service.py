import asyncio

from repositories import interaction_event_repository
from realtime import event_bus
from services import barrier_state_service
from services import interaction_event_service
from services import intervention_service
from services import multimodal_evidence_service
from services import scenario_service


async def run_intervention_pipeline(
    session_id: str,
    ui_context: dict,
    risk_result: dict | None = None,
    recent_events: list | None = None,
    speech_text: str = "",
    emotion_structured: dict | None = None,
    media_signals: dict | None = None,
    person_check: dict | None = None,
    multimodal_evidence: dict | None = None,
    scenario_id: str | None = None,
    source: str = "unknown",
    publish: bool = True,
) -> dict:
    """
    Patent-flow pipeline:
    POS events -> risk_score -> barrier_state -> intervention -> log -> realtime push.
    Routes should call this instead of duplicating barrier/intervention decisions.
    """
    safe_session_id = str(session_id or "anonymous")
    safe_ui_context = ui_context if isinstance(ui_context, dict) else {}
    events = recent_events if isinstance(recent_events, list) else await asyncio.to_thread(
        interaction_event_repository.get_recent_session_events,
        safe_session_id,
    )
    risk = risk_result if isinstance(risk_result, dict) and risk_result else (
        interaction_event_service.calculate_interaction_risk(events, safe_ui_context)
    )
    speech = str(speech_text or "")
    emotion = emotion_structured if isinstance(emotion_structured, dict) else {}
    media = media_signals if isinstance(media_signals, dict) else {}
    person = person_check if isinstance(person_check, dict) else {}
    normalized_scenario = scenario_service.normalize_scenario_id(scenario_id or "")
    if normalized_scenario not in scenario_service.MAIN_SCENARIO_IDS and events:
        normalized_scenario = scenario_service.infer_scenario_from_event(events[-1], risk)

    evidence = multimodal_evidence if isinstance(multimodal_evidence, dict) else None
    if evidence is None:
        evidence = multimodal_evidence_service.build_multimodal_evidence(
            emotion_structured=emotion,
            person_check=person,
            media_signals=media,
            speech_text=speech,
            risk_result=risk,
            ui_context=safe_ui_context,
            interaction_context=interaction_event_service.build_interaction_context(events, risk),
            emotion_available=bool(emotion),
            emotion_error=str(media.get("reason") or ""),
        )

    barrier_result = barrier_state_service.infer_barrier_state(
        emotion_structured=emotion,
        speech_text=speech,
        pos_events=events,
        ui_context=safe_ui_context,
        media_signals=media,
        risk_result=risk,
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
    should_log = (
        intervention.get("action") != "none"
        and barrier_result.get("barrier_state") != "normal_operation"
    )
    if should_log:
        log_payload = intervention_service.build_intervention_log(
            safe_session_id,
            barrier_result,
            intervention,
            safe_ui_context,
        )
        log_payload["source"] = source
        log_payload["multimodal_evidence"] = evidence
        if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
            scenario_service.attach_scenario_metadata(log_payload, normalized_scenario)
        log_payload["patent_category"] = barrier_result.get("patent_category")
        log_payload["patent_intervention_type"] = intervention.get("patent_intervention_type")
        intervention_log = await asyncio.to_thread(
            interaction_event_repository.append_intervention_log,
            log_payload,
        )

    result = {
        "risk_result": risk,
        "barrier_result": barrier_result,
        "intervention": intervention,
        "intervention_log": intervention_log,
        "multimodal_evidence": evidence,
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
