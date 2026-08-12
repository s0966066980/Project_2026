import json
import time
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import config
from capabilities.identity_access import device_identity_service
from capabilities.operations_configuration import observability_service
from realtime.connection_manager import ALLOWED_CLIENT_TYPES, manager
from utils.auth_utils import websocket_token_allowed


def _allowed_origins() -> set[str]:
    origins = set(config.CORS_ORIGINS or [])
    for origin in (config.PUBLIC_POS_ORIGIN, config.PUBLIC_ADMIN_ORIGIN):
        if origin:
            origins.add(origin)
    return {origin.rstrip("/") for origin in origins if origin}


def _origin_allowed(origin: str | None) -> bool:
    if not config.get("SECURITY_ENFORCED", config.is_security_enforced()) and not config.is_demo_public_mode():
        return True
    if not origin:
        return False
    parsed = urlparse(origin)
    if parsed.hostname in {"127.0.0.1", "0.0.0.0", "localhost", "::1"}:
        return True
    if (
        config.ENABLE_NGROK
        and parsed.hostname
        and (
            parsed.hostname.endswith(".ngrok-free.app")
            or parsed.hostname.endswith(".ngrok-free.dev")
            or parsed.hostname.endswith(".ngrok.io")
        )
    ):
        return True
    normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return normalized in _allowed_origins()


def _token_allowed(client_type: str, token: str) -> bool:
    return websocket_token_allowed(client_type, token)


def _websocket_identity_allowed(websocket: WebSocket, client_type: str) -> bool:
    cookie_name = str(config.get("DEVICE_SESSION_COOKIE_NAME", "kiosk_device_session"))
    if device_identity_service.authenticate_device_session(websocket.cookies.get(cookie_name, "")) is not None:
        return True
    return _token_allowed(client_type, websocket.query_params.get("token", ""))


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(tags=["realtime"])

    @router.websocket("/ws/{client_type}/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, client_type: str, session_id: str):
        client_type = str(client_type or "").lower()
        if client_type not in ALLOWED_CLIENT_TYPES:
            observability_service.increment_metric("websocket_connections_total", status="invalid_client")
            await websocket.close(code=1008)
            return
        if not _origin_allowed(websocket.headers.get("origin")):
            observability_service.increment_metric("websocket_connections_total", status="origin_denied")
            await websocket.close(code=1008)
            return
        if not _websocket_identity_allowed(websocket, client_type):
            observability_service.increment_metric("websocket_connections_total", status="auth_denied")
            await websocket.close(code=1008)
            return
        await manager.connect(client_type, session_id, websocket)
        observability_service.increment_metric("websocket_connections_total", status="connected")
        rate_window_started = time.monotonic()
        message_count = 0
        try:
            while True:
                try:
                    packet = await websocket.receive()
                except WebSocketDisconnect:
                    break
                except Exception:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "session_id": session_id,
                            "payload": {"message": "invalid websocket message"},
                        }
                    )
                    continue

                if packet.get("type") == "websocket.disconnect":
                    break
                text = packet.get("text")
                if text is not None and len(text) > 4096:
                    await websocket.close(code=1009)
                    break
                if text is None:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "session_id": session_id,
                            "payload": {"message": "text websocket message required"},
                        }
                    )
                    continue
                try:
                    message = json.loads(text or "{}")
                except Exception:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "session_id": session_id,
                            "payload": {"message": "invalid websocket message"},
                        }
                    )
                    continue

                if isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "session_id": session_id,
                            "payload": {"client_type": client_type},
                        }
                    )
                    continue

                now = time.monotonic()
                if now - rate_window_started >= 60:
                    rate_window_started = now
                    message_count = 0
                message_count += 1
                if message_count > 100:
                    await websocket.close(code=1013)
                    break
        finally:
            await manager.disconnect(client_type, session_id, websocket)
            observability_service.increment_metric("websocket_connections_total", status="disconnected")

    return router
