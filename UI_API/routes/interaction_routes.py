import asyncio
from collections import Counter

from fastapi import APIRouter, Body, Request

from repositories import interaction_event_repository
from services import interaction_event_service
from services import intervention_pipeline_service
from utils.auth_utils import require_admin_token


def _is_successful_intervention(log: dict) -> bool:
    result = log.get("result") if isinstance(log.get("result"), dict) else {}
    return bool(result.get("checkout_success") or result.get("payment_success"))


ISSUE_EVENT_TYPES = {
    "page_dwell_timeout",
    "back_navigation",
    "invalid_touch",
    "payment_failed",
    "checkout_error",
    "coupon_error",
    "customer_service_failed",
    "voice_order_failed",
}


def _build_intervention_stats(logs: list, events: list | None = None) -> dict:
    barrier_counts = Counter()
    patent_category_counts = Counter()
    action_counts = Counter()
    patent_intervention_counts = Counter()
    intervention_page_counts = Counter()
    event_page_issue_counts = Counter()
    event_rows = events or []

    for log in logs:
        if not isinstance(log, dict):
            continue
        barrier = log.get("barrier_result") if isinstance(log.get("barrier_result"), dict) else {}
        intervention = log.get("intervention") if isinstance(log.get("intervention"), dict) else {}
        ui_context = log.get("ui_context") if isinstance(log.get("ui_context"), dict) else {}

        barrier_state = str(barrier.get("barrier_state") or "unknown")
        patent_category = str(barrier.get("patent_category") or "unknown")
        action = str(intervention.get("action") or "unknown")
        patent_intervention = str(intervention.get("patent_intervention_type") or "unknown")
        page_id = str(ui_context.get("page_id") or "unknown")
        barrier_counts[barrier_state] += 1
        patent_category_counts[patent_category] += 1
        action_counts[action] += 1
        patent_intervention_counts[patent_intervention] += 1
        intervention_page_counts[page_id] += 1

    for event in event_rows:
        if not isinstance(event, dict):
            continue
        if str(event.get("event_type") or "") not in ISSUE_EVENT_TYPES:
            continue
        page_id = str(event.get("page_id") or "unknown")
        event_page_issue_counts[page_id] += 1

    total = len([row for row in logs if isinstance(row, dict)])
    success_count = sum(1 for row in logs if isinstance(row, dict) and _is_successful_intervention(row))
    combined_page_counts = intervention_page_counts + event_page_issue_counts
    return {
        "total_interventions": total,
        "success_count": success_count,
        "success_rate": round(success_count / total, 4) if total else 0,
        "barrier_state_counts": dict(barrier_counts),
        "patent_category_counts": dict(patent_category_counts),
        "action_counts": dict(action_counts),
        "patent_intervention_counts": dict(patent_intervention_counts),
        "intervention_page_counts": dict(intervention_page_counts),
        "event_page_issue_counts": dict(event_page_issue_counts),
        "page_issue_counts": dict(combined_page_counts),
        "recent_logs": list(reversed(logs[-20:])),
        "recent_events": list(reversed(event_rows[-20:])),
    }


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
    async def get_interaction_events(request: Request, session_id: str, limit: int = 200):
        require_admin_token(request)
        events = await asyncio.to_thread(
            interaction_event_repository.get_interaction_events, session_id, limit
        )
        return {"status": "success", "session_id": session_id, "events": events}

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
        pipeline_result = await intervention_pipeline_service.run_intervention_pipeline(
            session_id=session_id,
            ui_context=ui_context,
            recent_events=events,
            speech_text=speech_text,
            emotion_structured=emotion_structured,
            media_signals=media_signals,
            source="barrier_state",
        )
        return {
            "status": "success",
            "session_id": session_id,
            **pipeline_result,
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

    @router.get("/intervention_stats")
    async def get_intervention_stats(request: Request):
        require_admin_token(request)
        logs = await asyncio.to_thread(
            interaction_event_repository.get_intervention_logs, "", 3000
        )
        events = await asyncio.to_thread(
            interaction_event_repository.get_interaction_events, "", 3000
        )
        return {"status": "success", **_build_intervention_stats(logs, events)}

    return router
