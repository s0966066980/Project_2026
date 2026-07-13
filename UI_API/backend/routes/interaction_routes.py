import asyncio

from fastapi import APIRouter, Body, Request
from realtime import event_bus

import config
from repositories import interaction_event_repository
from services import interaction_event_service, intervention_pipeline_service, scenario_service, stats_service
from services.commercial_context_service import scope_from_admin_principal, scope_from_device_principal
from utils.auth_utils import authorize_admin_request, check_rate_limit, require_kiosk_token


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["interaction"])

    @router.post("/interaction_event")
    async def post_interaction_event(request: Request, payload: dict = Body(...)):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        check_rate_limit(request, "interaction_event", limit=180)
        event = interaction_event_service.normalize_interaction_event(payload)
        saved_event = await asyncio.to_thread(
            interaction_event_repository.append_interaction_event_scoped, event, scope
        )
        if event.get("event_type") == "payment_staff_requested":
            metadata = event.get("metadata") or {}
            emotion = metadata.get("emotion") if isinstance(metadata.get("emotion"), dict) else None
            assist_response = (emotion or {}).get("assist_response", "") if emotion else ""
            await event_bus.publish_to_admin(
                "staff_notify",
                {
                    "session_id": event.get("session_id", ""),
                    "kiosk_name": config.get("KIOSK_NAME", "機台01"),
                    "reason": "payment_staff_requested",
                    "emotion": emotion,
                    "assist_response": assist_response,
                },
            )
        return {"status": "success", "event": saved_event}

    @router.get("/interaction_events/{session_id}")
    async def get_interaction_events(request: Request, session_id: str, limit: int = 200):
        principal = authorize_admin_request(request, "operations.read")
        scope = scope_from_admin_principal(principal)
        events = await asyncio.to_thread(
            interaction_event_repository.get_interaction_events_scoped, scope, session_id, limit
        )
        return {"status": "success", "session_id": session_id, "events": events}

    @router.post("/barrier_state")
    async def post_barrier_state(request: Request, payload: dict = Body(...)):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        session_id = str(payload.get("session_id") or "")
        check_rate_limit(request, "barrier_state", limit=120, key=session_id)
        ui_context = payload.get("ui_context") if isinstance(payload.get("ui_context"), dict) else {}
        speech_text = str(payload.get("speech_text") or "")
        events = await asyncio.to_thread(
            interaction_event_repository.get_recent_session_events_scoped, scope, session_id
        )
        pipeline_result = await intervention_pipeline_service.run_intervention_pipeline(
            session_id=session_id,
            ui_context=ui_context,
            recent_events=events,
            speech_text=speech_text,
            source="barrier_state",
            scope=scope,
        )
        return {
            "status": "success",
            "session_id": session_id,
            **pipeline_result,
        }

    @router.post("/intervention_result")
    async def post_intervention_result(request: Request, payload: dict = Body(...)):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        check_rate_limit(request, "intervention_result", limit=120)
        intervention_id = str(payload.get("intervention_id") or "")
        result = {key: value for key, value in payload.items() if key != "intervention_id"}
        if not result.get("scenario_id") and intervention_id:
            logs = await asyncio.to_thread(interaction_event_repository.get_intervention_logs_scoped, scope, "", 3000)
            for log in reversed(logs):
                if str(log.get("intervention_id") or "") != intervention_id:
                    continue
                scenario_id = stats_service.scenario_from_log(log)
                if scenario_id:
                    result["scenario_id"] = scenario_id
                    result["scenario_label"] = scenario_service.get_scenario_definition(scenario_id).get("label", "")
                break
        updated = await asyncio.to_thread(
            interaction_event_repository.update_intervention_result_scoped,
            intervention_id,
            result,
            scope,
        )
        return {"status": "success" if updated else "not_found", "log": updated}

    @router.get("/intervention_stats")
    async def get_intervention_stats(request: Request):
        principal = authorize_admin_request(request, "operations.read")
        scope = scope_from_admin_principal(principal)
        logs = await asyncio.to_thread(interaction_event_repository.get_intervention_logs_scoped, scope, "", 3000)
        events = await asyncio.to_thread(interaction_event_repository.get_interaction_events_scoped, scope, "", 3000)
        return {"status": "success", **stats_service.build_intervention_stats(logs, events)}

    @router.delete("/intervention_logs")
    async def clear_intervention_logs(request: Request):
        principal = authorize_admin_request(request, "operations.write")
        scope = scope_from_admin_principal(principal)
        count = await asyncio.to_thread(interaction_event_repository.clear_intervention_logs_scoped, scope)
        return {"status": "success", "cleared": count}

    @router.delete("/interaction_events")
    async def clear_interaction_events(request: Request):
        principal = authorize_admin_request(request, "operations.write")
        scope = scope_from_admin_principal(principal)
        count = await asyncio.to_thread(interaction_event_repository.clear_interaction_events_scoped, scope)
        return {"status": "success", "cleared": count}

    return router
