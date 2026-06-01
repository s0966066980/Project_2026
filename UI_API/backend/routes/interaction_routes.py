import asyncio
from collections import Counter

from fastapi import APIRouter, Body, Request

from repositories import interaction_event_repository
from services import interaction_event_service
from services import intervention_pipeline_service
from services import scenario_service
from utils.auth_utils import require_admin_token


def _is_successful_intervention(log: dict) -> bool:
    result = log.get("result") if isinstance(log.get("result"), dict) else {}
    resolved_by = str(result.get("resolved_by") or "")
    return bool(
        result.get("checkout_success")
        or result.get("payment_success")
        or result.get("resolved")
        or result.get("resolved_by_checkout")
        or resolved_by in {"cart_add", "recommend_click", "payment_success", "checkout", "counter_payment"}
    )


def _scenario_from_log(log: dict) -> str:
    if not isinstance(log, dict):
        return ""
    candidates = [
        log.get("scenario_id"),
        (log.get("barrier_result") or {}).get("scenario_id") if isinstance(log.get("barrier_result"), dict) else "",
        (log.get("intervention") or {}).get("scenario_id") if isinstance(log.get("intervention"), dict) else "",
        (log.get("result") or {}).get("scenario_id") if isinstance(log.get("result"), dict) else "",
    ]
    for candidate in candidates:
        normalized = scenario_service.normalize_scenario_id(candidate or "")
        if normalized in scenario_service.MAIN_SCENARIO_IDS:
            return normalized
    barrier = log.get("barrier_result") if isinstance(log.get("barrier_result"), dict) else {}
    return scenario_service.infer_scenario_from_barrier_state(barrier.get("barrier_state", ""))


ISSUE_EVENT_TYPES = {
    "page_dwell_timeout",
    "back_navigation",
    "invalid_touch",
    "payment_failed",
    "checkout_error",
    "customer_service_failed",
    "voice_order_failed",
    "menu_page_dwell_timeout",
    "category_switch_repeat",
    "recommendation_ignored",
}


def _build_intervention_stats(logs: list, events: list | None = None) -> dict:
    barrier_counts = Counter()
    patent_category_counts = Counter()
    action_counts = Counter()
    patent_intervention_counts = Counter()
    intervention_page_counts = Counter()
    event_page_issue_counts = Counter()
    scenario_counts = Counter({scenario_id: 0 for scenario_id in scenario_service.MAIN_SCENARIO_IDS})
    scenario_success_counts = Counter({scenario_id: 0 for scenario_id in scenario_service.MAIN_SCENARIO_IDS})
    scenario_recent_logs = {scenario_id: [] for scenario_id in scenario_service.MAIN_SCENARIO_IDS}
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
        scenario_id = _scenario_from_log(log)
        if scenario_id in scenario_service.MAIN_SCENARIO_IDS:
            scenario_counts[scenario_id] += 1
            if _is_successful_intervention(log):
                scenario_success_counts[scenario_id] += 1
            scenario_recent_logs[scenario_id].append(log)

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
    scenario_success_rate = {
        scenario_id: (
            round(scenario_success_counts[scenario_id] / scenario_counts[scenario_id], 4)
            if scenario_counts[scenario_id]
            else 0
        )
        for scenario_id in scenario_service.MAIN_SCENARIO_IDS
    }
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
        "scenario_counts": dict(scenario_counts),
        "scenario_success_counts": dict(scenario_success_counts),
        "scenario_success_rate": scenario_success_rate,
        "scenario_recent_logs": {
            scenario_id: list(reversed(rows[-10:]))
            for scenario_id, rows in scenario_recent_logs.items()
        },
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
        return {"status": "success", "event": saved_event}

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
        speech_text = str(payload.get("speech_text") or "")
        events = await asyncio.to_thread(
            interaction_event_repository.get_recent_session_events, session_id
        )
        pipeline_result = await intervention_pipeline_service.run_intervention_pipeline(
            session_id=session_id,
            ui_context=ui_context,
            recent_events=events,
            speech_text=speech_text,
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
        if not result.get("scenario_id") and intervention_id:
            logs = await asyncio.to_thread(
                interaction_event_repository.get_intervention_logs, "", 3000
            )
            for log in reversed(logs):
                if str(log.get("intervention_id") or "") != intervention_id:
                    continue
                scenario_id = _scenario_from_log(log)
                if scenario_id:
                    result["scenario_id"] = scenario_id
                    result["scenario_label"] = scenario_service.get_scenario_definition(scenario_id).get("label", "")
                break
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

    @router.delete("/intervention_logs")
    async def clear_intervention_logs(request: Request):
        require_admin_token(request)
        count = await asyncio.to_thread(interaction_event_repository.clear_intervention_logs)
        return {"status": "success", "cleared": count}

    @router.delete("/interaction_events")
    async def clear_interaction_events(request: Request):
        require_admin_token(request)
        count = await asyncio.to_thread(interaction_event_repository.clear_interaction_events)
        return {"status": "success", "cleared": count}

    return router
