import asyncio

from fastapi import APIRouter, Body

from repositories import interaction_event_repository
from realtime import event_bus
from services import barrier_state_service
from services import interaction_event_service
from services import intervention_service


SCENARIOS = {
    "payment_failed": {
        "page_id": "payment_page",
        "event_type": "payment_failed",
        "button_id": "demo_payment",
        "dwell_time_sec": 35,
        "payment_fail_count": 1,
        "speech_text": "付款一直失敗，請協助我完成付款。",
        "metadata": {"source": "demo", "payment": "failed"},
    },
    "long_payment_dwell": {
        "page_id": "payment_page",
        "event_type": "page_dwell_timeout",
        "button_id": "demo_timer",
        "dwell_time_sec": 45,
        "speech_text": "我停在付款頁很久，不知道下一步。",
        "metadata": {"source": "demo", "reason": "long_dwell"},
    },
    "invalid_touch": {
        "page_id": "menu_page",
        "event_type": "invalid_touch",
        "button_id": "demo_invalid_touch",
        "invalid_touch_count": 3,
        "dwell_time_sec": 20,
        "speech_text": "我看不懂怎麼點。",
        "metadata": {"source": "demo", "reason": "invalid_touch"},
    },
    "coupon_error": {
        "page_id": "coupon_page",
        "event_type": "coupon_error",
        "button_id": "demo_coupon",
        "coupon_error_count": 1,
        "dwell_time_sec": 28,
        "speech_text": "優惠券掃碼失敗，折扣碼不能用。",
        "metadata": {"source": "demo", "reason": "coupon_error"},
    },
    "back_navigation": {
        "page_id": "checkout_page",
        "event_type": "back_navigation",
        "button_id": "demo_back",
        "back_count": 2,
        "dwell_time_sec": 32,
        "speech_text": "我一直返回，不知道要怎麼確認餐點。",
        "metadata": {"source": "demo", "reason": "back_navigation"},
    },
    "customer_service_requested": {
        "page_id": "menu_page",
        "event_type": "customer_service_requested",
        "button_id": "demo_service",
        "dwell_time_sec": 31,
        "speech_text": "我需要客服幫忙操作。",
        "metadata": {"source": "demo", "reason": "customer_service_requested"},
    },
    "complaint_risk": {
        "page_id": "payment_page",
        "event_type": "payment_failed",
        "button_id": "demo_complaint",
        "payment_fail_count": 1,
        "dwell_time_sec": 38,
        "speech_text": "付款一直失敗，太誇張了，我要找經理客訴。",
        "metadata": {"source": "demo", "reason": "complaint_risk"},
    },
}


def _scenario_payload(payload: dict) -> tuple[dict, str]:
    scenario = str((payload or {}).get("scenario") or "payment_failed")
    base = dict(SCENARIOS.get(scenario) or SCENARIOS["payment_failed"])
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
    return event, speech_text


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/demo", tags=["demo"])

    @router.post("/trigger_scenario")
    async def trigger_scenario(payload: dict = Body(default={})):
        event_payload, speech_text = _scenario_payload(payload)
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
            "scenario": str((payload or {}).get("scenario") or "payment_failed"),
            "event": saved_event,
            "risk_result": risk_result,
            "barrier_result": None,
            "intervention": None,
            "intervention_log": None,
        }

        if not risk_result.get("triggered"):
            return response

        barrier_result = barrier_state_service.infer_barrier_state(
            emotion_structured={},
            speech_text=speech_text,
            pos_events=recent_events,
            ui_context=ui_context,
            media_signals={},
            risk_result=risk_result,
        )
        intervention = intervention_service.decide_intervention(barrier_result, ui_context)
        intervention_log = None
        if (
            intervention.get("action") != "none"
            and barrier_result.get("barrier_state") != "normal_operation"
        ):
            log_payload = intervention_service.build_intervention_log(
                session_id, barrier_result, intervention, ui_context
            )
            intervention_log = await asyncio.to_thread(
                interaction_event_repository.append_intervention_log, log_payload
            )
            event_payload = {
                "barrier_result": barrier_result,
                "intervention": intervention,
                "intervention_log": intervention_log,
                "risk_result": risk_result,
                "demo": True,
                "source": "demo_trigger_scenario",
            }
            await event_bus.publish_intervention(session_id, event_payload)

        response.update({
            "barrier_result": barrier_result,
            "intervention": intervention,
            "intervention_log": intervention_log,
        })
        return response

    return router
