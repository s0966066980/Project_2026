"""Emotion-LLaMA 路由。"""
import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from repositories import emotion_log_repository
from services import emotion_service
from utils.auth_utils import check_rate_limit, read_limited_upload, require_admin_token, require_kiosk_token
from utils.file_utils import write_binary_file


async def _save_upload_temp(media: UploadFile) -> str:
    media_bytes = await read_limited_upload(media)
    suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        temp_path = tmp.name
    await asyncio.to_thread(write_binary_file, temp_path, media_bytes)
    return temp_path


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/emotion", tags=["emotion"])

    @router.post("/analyze_event")
    async def analyze_emotion_event(
        request: Request,
        session_id: str = Form(...),
        event_type: str = Form(...),
        speech_text: str = Form(""),
        media: UploadFile = File(...),
    ):
        """事件驅動分析：截片送 Emotion-LLaMA，結果寫 log。"""
        require_kiosk_token(request)
        check_rate_limit(request, "emotion_analyze", limit=30, key=session_id)
        temp_path = None
        try:
            temp_path = await _save_upload_temp(media)
            return await emotion_service.analyze_event(
                session_id=session_id,
                media_path=temp_path,
                event_type=event_type,
                speech_text=speech_text,
            )
        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    @router.get("/intervention_logs")
    async def get_intervention_logs(request: Request, limit: int = 200):
        """Admin 統計：取得 Emotion-LLaMA 介入紀錄。"""
        require_admin_token(request)
        logs = await asyncio.to_thread(emotion_log_repository.get_logs, limit)
        return {"status": "success", "logs": logs, "total": len(logs)}

    @router.delete("/intervention_logs")
    async def clear_intervention_logs(request: Request):
        require_admin_token(request)
        count = await asyncio.to_thread(emotion_log_repository.clear_logs)
        return {"status": "success", "cleared": count}

    return router
