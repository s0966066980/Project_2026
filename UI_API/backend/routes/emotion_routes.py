"""Emotion-LLaMA 路由。"""
import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from repositories import emotion_log_repository
from services import emotion_service
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/emotion", tags=["emotion"])

    @router.post("/analyze")
    async def analyze_emotion(
        session_id: str = Form(...),
        media: UploadFile = File(...),
    ):
        temp_path = None
        try:
            suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_path = tmp.name
            media_bytes = await media.read()
            await asyncio.to_thread(write_binary_file, temp_path, media_bytes)
            return await emotion_service.analyze(session_id=session_id, media_path=temp_path)
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    @router.post("/analyze_event")
    async def analyze_emotion_event(
        session_id: str = Form(...),
        event_type: str = Form(...),
        media: UploadFile = File(...),
    ):
        """事件驅動分析：截片送 Emotion-LLaMA，結果寫 log。"""
        temp_path = None
        try:
            suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_path = tmp.name
            media_bytes = await media.read()
            await asyncio.to_thread(write_binary_file, temp_path, media_bytes)
            result = await emotion_service.analyze_event(
                session_id=session_id,
                media_path=temp_path,
                event_type=event_type,
            )
            return result
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    @router.get("/intervention_logs")
    async def get_intervention_logs(limit: int = 200):
        """Admin 統計：取得 Emotion-LLaMA 介入紀錄。"""
        logs = await asyncio.to_thread(emotion_log_repository.get_logs, limit)
        return {"status": "success", "logs": logs, "total": len(logs)}

    @router.delete("/intervention_logs")
    async def clear_intervention_logs():
        count = await asyncio.to_thread(emotion_log_repository.clear_logs)
        return {"status": "success", "cleared": count}

    return router
