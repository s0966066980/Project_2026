"""Emotion settings support, live media test, and minimal 30-day records."""

import asyncio
import os
import tempfile
from typing import Literal

from fastapi import APIRouter, File, Form, Request, UploadFile

from repositories import emotion_log_repository
from services import emotion_service
from utils.auth_utils import authorize_admin_request, check_rate_limit, read_limited_upload, require_kiosk_token
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

    @router.get("/profiles")
    async def profiles(request: Request):
        authorize_admin_request(request, "system.debug")
        return {
            "status": "success",
            "profiles": emotion_service.model_profiles(),
            "default_profile": emotion_service.MODEL_PROFILE,
            "default_prompt": emotion_service.default_prompt(),
            "duration": {"min": 2, "max": 30, "default": 5},
        }

    @router.get("/readiness")
    async def readiness(request: Request):
        """Lightweight Kiosk gate; no media should be captured while false."""
        require_kiosk_token(request)
        profile = emotion_service.model_profiles()[0]
        return {
            "status": "ready" if profile.get("ready") else "unavailable",
            "ready": bool(profile.get("ready")),
            "provider": profile,
        }

    @router.post("/analyze_event")
    async def analyze_emotion_event(
        request: Request,
        session_id: str = Form(...),
        event_type: Literal["voice_mode_ended", "ordering_periodic"] = Form(...),
        media: UploadFile = File(...),
    ):
        require_kiosk_token(request)
        check_rate_limit(request, "emotion_analyze", limit=30, key=session_id)
        temp_path = await _save_upload_temp(media)
        try:
            return await emotion_service.analyze_event(
                session_id=session_id,
                media_path=temp_path,
                event_type=event_type,
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @router.post("/analyze_media_test")
    async def analyze_media_test(
        request: Request,
        media: UploadFile = File(...),
        model_profile: str = Form("r1_omni"),
        prompt: str = Form(""),
    ):
        authorize_admin_request(request, "system.debug")
        check_rate_limit(request, "emotion_media_test", limit=60)
        temp_path = await _save_upload_temp(media)
        try:
            return await emotion_service.analyze_live_diagnostic(
                temp_path,
                model_profile=model_profile,
                prompt=prompt[:20_000],
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @router.get("/records")
    async def records(request: Request, limit: int = 200):
        authorize_admin_request(request, "operations.read")
        rows = await asyncio.to_thread(emotion_log_repository.get_records, limit)
        return {"status": "success", "records": rows, "total": len(rows), "retention_days": 30}

    @router.delete("/records")
    async def clear_records(request: Request):
        authorize_admin_request(request, "operations.write")
        count = await asyncio.to_thread(emotion_log_repository.clear_records)
        return {"status": "success", "cleared": count}

    return router
