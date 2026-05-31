"""語音助理路由。"""
import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

from services import voice_service
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["voice"])

    @router.post("/ask")
    async def process_voice(
        session_id: str = Form(...),
        media: UploadFile = File(...),
        multi_lang: str = Form(default="true"),
    ):
        temp_path = None
        try:
            suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_path = tmp.name
            media_bytes = await media.read()
            await asyncio.to_thread(write_binary_file, temp_path, media_bytes)
            return await voice_service.handle_voice(
                session_id=session_id,
                audio_path=temp_path,
                ollama_semaphore=deps["ollama_semaphore"],
                multi_lang=multi_lang.lower() == "true",
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    return router
