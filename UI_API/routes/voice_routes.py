import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

from services import voice_assist_service
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["voice"])

    @router.post("/ask")
    async def process_voice_assist(
        session_id: str = Form(...),
        audio: UploadFile = File(...),
        multi_lang: str = Form(default="true"),
    ):
        temp_audio_path = None
        try:
            suffix = os.path.splitext(audio.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_audio_path = tmp.name
            audio_bytes = await audio.read()
            await asyncio.to_thread(write_binary_file, temp_audio_path, audio_bytes)

            # Emotion context injected if available from current session
            emotion_structured = (deps.get("emotion_cache") or {}).get(session_id, {}).get("emotion_structured")

            return await voice_assist_service.handle_voice_assist(
                session_id=session_id,
                audio_path=temp_audio_path,
                multi_lang=multi_lang.lower() == "true",
                ollama_semaphore=deps["ollama_semaphore"],
                emotion_structured=emotion_structured,
            )
        except Exception as e:
            print(f"❌ voice_assist 錯誤: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)

    return router
