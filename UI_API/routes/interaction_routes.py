import asyncio

from fastapi import APIRouter, Body

from repositories import interaction_event_repository
from services import barrier_state_service
from services import interaction_event_service
from services import intervention_service


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["interaction"])

    @router.post("/interaction_event")
    async def post_interaction_event(payload: dict = Body(...)):
        event = interaction_event_service.normalize_interaction_event(payload)
        saved_event = await asyncio.to_thread(
            interaction_event_repository.append_interaction_event, event
        )
        recent_events = await asyncio.to_thread(
            interaction_event_repository.get_recent_session_events,
            saved_event.get("session_id", ""),
        )
        ui_context = payload.get("ui_context") if isinstance(payload.get("ui_context"), dict) else {}
        risk_result = interaction_event_service.calculate_interaction_risk(recent_events, ui_context)
        return {"status": "success", "event": saved_event, "risk_result": risk_result}

    @router.get("/interaction_events/{session_id}")
    async def get_interaction_events(session_id: str, limit: int = 200):
        events = await asyncio.to_thread(
            interaction_event_repository.get_interaction_events, session_id, limit
        )
        return {"status": "success", "session_id": session_id, "events": events}

    @router.post("/interaction_risk")
    async def post_interaction_risk(payload: dict = Body(...)):
        session_id = str(payload.get("session_id") or "")
        ui_context = payload.get("ui_context") if isinstance(payload.get("ui_context"), dict) else {}
        events = await asyncio.to_thread(
            interaction_event_repository.get_recent_session_events, session_id
        )
        risk_result = interaction_event_service.calculate_interaction_risk(events, ui_context)
        context = interaction_event_service.build_interaction_context(events, risk_result)
        return {
            "status": "success",
            "session_id": session_id,
            "risk_result": risk_result,
            "interaction_context": context,
        }

    @router.post("/barrier_state")
    async def post_barrier_state(payload: dict = Body(...)):
        session_id = str(payload.get("session_id") or "")
        ui_context = payload.get("ui_context") if isinstance(payload.get("ui_context"), dict) else {}
        emotion_structured = (
            payload.get("emotion_structured")
            if isinstance(payload.get("emotion_structured"), dict)
            else {}
        )
        media_signals = (
            payload.get("media_signals")
            if isinstance(payload.get("media_signals"), dict)
            else {}
        )
        speech_text = str(payload.get("speech_text") or "")
        events = await asyncio.to_thread(
            interaction_event_repository.get_recent_session_events, session_id
        )
        risk_result = interaction_event_service.calculate_interaction_risk(events, ui_context)
        barrier_result = barrier_state_service.infer_barrier_state(
            emotion_structured=emotion_structured,
            speech_text=speech_text,
            pos_events=events,
            ui_context=ui_context,
            media_signals=media_signals,
            risk_result=risk_result,
        )
        intervention = intervention_service.decide_intervention(barrier_result, ui_context)
        log_payload = intervention_service.build_intervention_log(
            session_id, barrier_result, intervention, ui_context
        )
        intervention_log = await asyncio.to_thread(
            interaction_event_repository.append_intervention_log, log_payload
        )
        return {
            "status": "success",
            "session_id": session_id,
            "risk_result": risk_result,
            "barrier_result": barrier_result,
            "intervention": intervention,
            "intervention_log": intervention_log,
        }

    @router.post("/intervention_result")
    async def post_intervention_result(payload: dict = Body(...)):
        intervention_id = str(payload.get("intervention_id") or "")
        result = {key: value for key, value in payload.items() if key != "intervention_id"}
        updated = await asyncio.to_thread(
            interaction_event_repository.update_intervention_result,
            intervention_id,
            result,
        )
        return {"status": "success" if updated else "not_found", "log": updated}

    @router.get("/intervention_logs/{session_id}")
    async def get_intervention_logs(session_id: str, limit: int = 200):
        logs = await asyncio.to_thread(
            interaction_event_repository.get_intervention_logs, session_id, limit
        )
        return {"status": "success", "session_id": session_id, "logs": logs}

    return router
