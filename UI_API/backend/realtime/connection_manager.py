import asyncio
from collections import defaultdict
from typing import Any

ALLOWED_CLIENT_TYPES = {"pos", "admin", "demo"}


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, dict[str, set[Any]]] = {
            client_type: defaultdict(set) for client_type in ALLOWED_CLIENT_TYPES
        }
        self._lock = asyncio.Lock()

    @staticmethod
    def _session_key(client_type: str, session_id: str) -> str:
        if client_type == "admin":
            return "global"
        return str(session_id or "global")

    async def connect(self, client_type: str, session_id: str, websocket):
        client_type = str(client_type or "").lower()
        if client_type not in ALLOWED_CLIENT_TYPES:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        session_key = self._session_key(client_type, session_id)
        async with self._lock:
            self.active_connections[client_type][session_key].add(websocket)

    async def disconnect(self, client_type: str, session_id: str, websocket):
        client_type = str(client_type or "").lower()
        if client_type not in ALLOWED_CLIENT_TYPES:
            return
        session_key = self._session_key(client_type, session_id)
        async with self._lock:
            sockets = self.active_connections[client_type].get(session_key)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self.active_connections[client_type].pop(session_key, None)

    async def _send_many(self, targets: list[tuple[str, str, Any]], payload: dict):
        dead: list[tuple[str, str, Any]] = []
        for client_type, session_key, websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:
                dead.append((client_type, session_key, websocket))
        if not dead:
            return
        async with self._lock:
            for client_type, session_key, websocket in dead:
                sockets = self.active_connections.get(client_type, {}).get(session_key)
                if not sockets:
                    continue
                sockets.discard(websocket)
                if not sockets:
                    self.active_connections[client_type].pop(session_key, None)

    async def send_to_client_type(self, client_type: str, payload: dict):
        client_type = str(client_type or "").lower()
        targets: list[tuple[str, str, Any]] = []
        async with self._lock:
            for session_key, sockets in self.active_connections.get(client_type, {}).items():
                for websocket in sockets.copy():
                    targets.append((client_type, session_key, websocket))
        await self._send_many(targets, payload)

    async def send_to_client_session(self, client_type: str, session_id: str, payload: dict):
        client_type = str(client_type or "").lower()
        session_key = self._session_key(client_type, session_id)
        targets: list[tuple[str, str, Any]] = []
        async with self._lock:
            for websocket in self.active_connections.get(client_type, {}).get(session_key, set()).copy():
                targets.append((client_type, session_key, websocket))
        await self._send_many(targets, payload)

    async def broadcast_admin(self, payload: dict):
        await self.send_to_client_type("admin", payload)

    async def broadcast_all(self, payload: dict):
        targets: list[tuple[str, str, Any]] = []
        async with self._lock:
            for client_type, sessions in self.active_connections.items():
                for session_key, sockets in sessions.items():
                    for websocket in sockets.copy():
                        targets.append((client_type, session_key, websocket))
        await self._send_many(targets, payload)


manager = ConnectionManager()
