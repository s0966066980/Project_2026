"""Emotion-LLaMA 路由 — stub，預留對接介面。"""
import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

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
            return await emotion_service.analyze(
                session_id=session_id,
                media_path=temp_path,
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    return router
