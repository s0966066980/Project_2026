import time
from fastapi import APIRouter
from pydantic import BaseModel

class PosEvent(BaseModel):
    session_id: str
    event_type: str
    timestamp: float = None
    details: dict = {}

def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/monitor", tags=["monitor"])

    @router.post("/pos_event")
    async def log_pos_event(event: PosEvent):
        if not event.timestamp:
            event.timestamp = time.time()
            
        # Here we would implement the logic to handle abnormal events
        # e.g., if event_type == "stuck", trigger Emotion-LLaMA or alert clerk
        if event.event_type in ["idle_timeout", "repeated_errors", "stuck"]:
            # Example: Triggering clerk assistance flag
            print(f"⚠️ [Monitor] Abnormal POS event detected for session {event.session_id}: {event.event_type}")
            # Logic to notify clerk side would go here...

        return {"status": "success", "event_logged": True}

    return router
