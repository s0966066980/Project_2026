"""Emotion-LLaMA 路由。"""

import asyncio
import os
import tempfile
from typing import Literal

import config
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from repositories import emotion_log_repository
from services import emotion_service
from utils.auth_utils import authorize_admin_request, check_rate_limit, read_limited_upload, require_kiosk_token
from utils.file_utils import write_binary_file


class EmotionTextAnalysisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class EmotionRoundAnalysisRequest(BaseModel):
    emotion_round_id: str = Field(min_length=1, max_length=80)


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
        event_type: Literal["voice_mode_started", "voice_mode_ended"] = Form(...),
        emotion_round_id: str = Form(""),
        voice_turn_id: str = Form(""),
        voice_turn_index: int = Form(0),
        observed_at_ms: int = Form(0),
        speech_text: str = Form(""),
        media: UploadFile = File(...),
    ):
        """事件驅動分析：截片送 Emotion-LLaMA，結果寫 log。"""
        require_kiosk_token(request)
        check_rate_limit(request, "emotion_analyze", limit=30, key=session_id)
        temp_path = None
        try:
            safe_speech_text = (
                speech_text.strip()[:500]
                if event_type == "voice_mode_ended"
                and config.get("EMOTION_LLAMA_INCLUDE_STT", True)
                else ""
            )
            temp_path = await _save_upload_temp(media)
            return await emotion_service.analyze_event(
                session_id=session_id,
                media_path=temp_path,
                event_type=event_type,
                speech_text=safe_speech_text,
                update_voice_session=True,
                emotion_round_id=emotion_round_id,
                voice_turn_id=voice_turn_id,
                voice_turn_index=voice_turn_index,
                observed_at_ms=observed_at_ms,
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
        """Admin 統計：取得 Emotion-LLaMA 分析紀錄。"""
        authorize_admin_request(request, "operations.read")
        logs = await asyncio.to_thread(emotion_log_repository.get_logs, limit)
        return {"status": "success", "logs": logs, "total": len(logs)}

    @router.post("/analyze_text")
    async def analyze_emotion_text(payload: EmotionTextAnalysisRequest, request: Request):
        """Admin-only text simulation; returns evidence and never performs a transaction."""
        authorize_admin_request(request, "system.debug")
        check_rate_limit(request, "emotion_text_analyze", limit=30)
        text = payload.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="text 不可為空")
        return await emotion_service.analyze_text(text)

    @router.post("/analyze_ordering_round")
    async def analyze_ordering_round(payload: EmotionRoundAnalysisRequest, request: Request):
        """Admin-only LLM test over complete emotion evidence from one ordering round."""
        authorize_admin_request(request, "system.debug")
        check_rate_limit(request, "emotion_round_analyze", limit=20)
        try:
            return await emotion_service.analyze_ordering_round(payload.emotion_round_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/analyze_media_test")
    async def analyze_emotion_media_test(
        request: Request,
        media: UploadFile = File(...),
        speech_text: str = Form(""),
    ):
        """Admin-only camera test; records evidence but never updates intervention state."""
        authorize_admin_request(request, "system.debug")
        check_rate_limit(request, "emotion_media_test", limit=20)
        temp_path = None
        try:
            temp_path = await _save_upload_temp(media)
            return await emotion_service.analyze_event(
                session_id="admin_media_test",
                media_path=temp_path,
                event_type="admin_media_test",
                speech_text=speech_text.strip()[:500],
                update_voice_session=False,
            )
        except HTTPException:
            raise
        except Exception as exc:
            print(f"⚠️ Admin emotion media test failed: {exc}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "影像分析暫時無法完成"},
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    @router.delete("/intervention_logs")
    async def clear_intervention_logs(request: Request):
        authorize_admin_request(request, "operations.write")
        count = await asyncio.to_thread(emotion_log_repository.clear_logs)
        return {"status": "success", "cleared": count}

    return router
