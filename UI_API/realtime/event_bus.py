import time

from realtime.connection_manager import manager


EVENT_TYPES = {
    "human_reply",
    "customer_service_request",
    "interaction_intervention",
    "emotion_analysis_started",
    "emotion_analysis_completed",
    "staff_notify",
    "settings_changed",
    "demo_event",
}


def _build_event(event_type: str, session_id: str = "", payload: dict | None = None) -> dict:
    return {
        "type": str(event_type or "demo_event"),
        "session_id": str(session_id or ""),
        "payload": payload if isinstance(payload, dict) else {},
        "timestamp": time.time(),
    }


async def publish_event(event: dict):
    payload = dict(event or {})
    payload.setdefault("type", "demo_event")
    payload.setdefault("session_id", "")
    payload.setdefault("payload", {})
    payload.setdefault("timestamp", time.time())
    await manager.broadcast_all(payload)
    return payload


async def publish_to_pos(session_id: str, event_type: str, payload: dict):
    event = _build_event(event_type, session_id, payload)
    await manager.send_to_client_session("pos", session_id, event)
    return event


async def publish_to_admin(event_type: str, payload: dict):
    event = _build_event(event_type, "", payload)
    await manager.broadcast_admin(event)
    return event


async def publish_to_demo(session_id: str, event_type: str, payload: dict):
    event = _build_event(event_type, session_id, payload)
    await manager.send_to_client_session("demo", session_id, event)
    return event
