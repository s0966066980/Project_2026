"""語音助理路由。"""
import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from services import voice_service
from services.commercial_context_service import scope_from_device_principal
from utils.auth_utils import check_rate_limit, read_limited_upload, require_kiosk_token
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["voice"])

    @router.post("/ask")
    async def process_voice(
        request: Request,
        session_id: str = Form(...),
        media: UploadFile = File(...),
        multi_lang: str = Form(default="true"),
    ):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        check_rate_limit(request, "voice_ask", limit=30, key=session_id)
        temp_path = None
        try:
            suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_path = tmp.name
            media_bytes = await read_limited_upload(media)
            await asyncio.to_thread(write_binary_file, temp_path, media_bytes)
            return await voice_service.handle_voice(
                session_id=session_id,
                audio_path=temp_path,
                ollama_semaphore=deps["ollama_semaphore"],
                multi_lang=multi_lang.lower() == "true",
                scope=scope,
            )
        except HTTPException:
            raise
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    @router.post("/ask/stream")
    async def process_voice_stream(
        request: Request,
        session_id: str = Form(...),
        media: UploadFile = File(...),
        multi_lang: str = Form(default="true"),
    ):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        check_rate_limit(request, "voice_stream", limit=30, key=session_id)
        media_bytes = await read_limited_upload(media)
        suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
        await asyncio.to_thread(write_binary_file, temp_path, media_bytes)

        async def _stream_with_cleanup():
            try:
                async for chunk in voice_service.handle_voice_stream(
                    session_id=session_id,
                    audio_path=temp_path,
                    ollama_semaphore=deps["ollama_semaphore"],
                    multi_lang=multi_lang.lower() == "true",
                    scope=scope,
                ):
                    yield chunk
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        return StreamingResponse(
            _stream_with_cleanup(),
            media_type="application/x-ndjson",
        )

    return router
