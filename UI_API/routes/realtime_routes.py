from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from realtime.connection_manager import ALLOWED_CLIENT_TYPES, manager


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(tags=["realtime"])

    @router.websocket("/ws/{client_type}/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, client_type: str, session_id: str):
        client_type = str(client_type or "").lower()
        if client_type not in ALLOWED_CLIENT_TYPES:
            await websocket.close(code=1008)
            return
        await manager.connect(client_type, session_id, websocket)
        try:
            while True:
                try:
                    message = await websocket.receive_json()
                except WebSocketDisconnect:
                    break
                except Exception:
                    await websocket.send_json({
                        "type": "error",
                        "session_id": session_id,
                        "payload": {"message": "invalid websocket message"},
                    })
                    continue

                if isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "session_id": session_id,
                        "payload": {"client_type": client_type},
                    })
        finally:
            await manager.disconnect(client_type, session_id, websocket)

    return router
