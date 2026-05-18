import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

from services import voice_order_service
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["voice"])

    @router.post("/ask")
    async def process_ask(
        session_id: str = Form(...),
        audio: UploadFile = File(...),
        multi_lang: str = Form(default="true"),
        use_ollama: str = Form(default="true")
    ):
        temp_audio_path = None
        try:
            suffix = os.path.splitext(audio.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_audio_path = tmp.name
            audio_bytes = await audio.read()
            await asyncio.to_thread(write_binary_file, temp_audio_path, audio_bytes)
            return await voice_order_service.handle_voice_ask(
                session_id=session_id,
                audio_path=temp_audio_path,
                multi_lang=multi_lang.lower() == "true",
                use_ollama=use_ollama.lower() == "true",
                ollama_semaphore=deps["ollama_semaphore"],
                schedule_rag_rebuild=deps.get("schedule_rag_rebuild"),
            )
        except Exception as e:
            print(f"❌ ask 錯誤: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)

    return router
