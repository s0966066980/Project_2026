import asyncio
import os
import tempfile

from fastapi import APIRouter, Body, File, Form, UploadFile
from fastapi.responses import FileResponse

import ai_services
import config
from repositories import log_repository
from services import customer_service_handler
from utils.file_utils import write_binary_file
from utils.text_utils import to_traditional_lite


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["customer-service"])

    @router.get("/customer_service_logs")
    async def get_customer_service_logs():
        logs = await asyncio.to_thread(log_repository.get_customer_service_logs)
        return {"logs": logs[-300:]}

    @router.get("/customer_service_media/{filename}")
    async def get_customer_service_media(filename: str):
        safe_name = os.path.basename(filename)
        media_path = os.path.join(config.CUSTOMER_SERVICE_MEDIA_DIR, safe_name)
        if not os.path.exists(media_path):
            return {"status": "not_found"}
        return FileResponse(media_path)

    @router.post("/customer_service_logs/{source_id}/human_reply")
    async def customer_service_human_reply(source_id: str, payload: dict = Body(...)):
        reply = (payload.get("reply") or "").strip()
        lang = payload.get("language") or "zh"
        if not reply:
            return {"status": "error", "message": "reply is required"}
        if lang != "en":
            reply = to_traditional_lite(reply)
        updated = await asyncio.to_thread(log_repository.update_customer_service_log, source_id, {
            "human_reply": reply,
            "customer_reply": reply,
            "mode": "human_replied",
            "reply_language": lang
        })
        if not updated:
            return {"status": "not_found"}
        audio_base64 = await ai_services.generate_tts_audio_base64(reply, lang=lang)
        return {"status": "success", "log": updated, "audio_base64": audio_base64}

    @router.post("/customer_service")
    async def process_customer_service(
        session_id: str = Form(...),
        media: UploadFile = File(...),
        use_ollama: str = Form(default="true"),
        multi_lang: str = Form(default="true")
    ):
        temp_media_path = None
        try:
            suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_media_path = tmp.name
            media_bytes = await media.read()
            await asyncio.to_thread(write_binary_file, temp_media_path, media_bytes)
            return await customer_service_handler.handle_customer_service(
                session_id=session_id,
                media_path=temp_media_path,
                suffix=suffix,
                multi_lang=multi_lang.lower() == "true",
                use_ollama=use_ollama.lower() == "true",
                deps=deps,
            )
        except Exception as e:
            print(f"❌ customer_service 錯誤: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if temp_media_path and os.path.exists(temp_media_path):
                os.remove(temp_media_path)

    return router
