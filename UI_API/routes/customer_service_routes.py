import asyncio
import os
import tempfile

from fastapi import APIRouter, Body, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

import ai_services
import config
from repositories import log_repository
from realtime import event_bus
from services import customer_service_handler
from utils.auth_utils import require_admin_token
from utils.file_utils import write_binary_file
from utils.text_utils import to_traditional_lite


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["customer-service"])

    @router.get("/customer_service_logs")
    async def get_customer_service_logs(request: Request):
        require_admin_token(request)
        logs = await asyncio.to_thread(log_repository.get_customer_service_logs)
        return {"logs": logs[-300:]}

    @router.get("/customer_service_media/{filename}")
    async def get_customer_service_media(request: Request, filename: str):
        require_admin_token(request)
        safe_name = os.path.basename(filename)
        media_path = os.path.join(config.CUSTOMER_SERVICE_MEDIA_DIR, safe_name)
        if not os.path.exists(media_path):
            return {"status": "not_found"}
        return FileResponse(media_path)

    @router.post("/customer_service_logs/{source_id}/human_reply")
    async def customer_service_human_reply(request: Request, source_id: str, payload: dict = Body(...)):
        require_admin_token(request)
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
        await event_bus.publish_to_pos(str(updated.get("session_id") or ""), "human_reply", {
            "source_id": source_id,
            "reply": reply,
            "audio_base64": audio_base64,
            "language": lang,
            "customer_service_state": updated.get("customer_service_state"),
            "priority": updated.get("priority"),
        })
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
            use_ollama_bool = use_ollama.lower() == "true"
            multi_lang_bool = multi_lang.lower() == "true"
            if not use_ollama_bool:
                await event_bus.publish_to_admin("customer_service_request", {
                    "session_id": session_id,
                    "source_id": "",
                    "user_text": "",
                    "emotion": "pending",
                    "customer_service_state": "pending",
                    "needs_human_staff": True,
                    "priority": "normal",
                    "mode": "human_pending",
                    "message": "POS 顧客已請求真人客服，背景語音與情緒分析中",
                })

                async def _background_human_service(path: str):
                    try:
                        result = await customer_service_handler.handle_customer_service(
                            session_id=session_id,
                            media_path=path,
                            suffix=suffix,
                            multi_lang=multi_lang_bool,
                            use_ollama=False,
                            deps=deps,
                        )
                        if result.get("status") == "success":
                            await event_bus.publish_to_admin("customer_service_request", {
                                "session_id": session_id,
                                "source_id": result.get("source_id", ""),
                                "user_text": result.get("user_text", ""),
                                "emotion": result.get("emotion", ""),
                                "customer_service_state": result.get("customer_service_state", ""),
                                "needs_human_staff": True,
                                "priority": result.get("priority", "normal"),
                                "mode": "human_analysis_completed",
                            })
                    except Exception as bg_error:
                        print(f"❌ customer_service 背景處理錯誤: {bg_error}")
                    finally:
                        if path and os.path.exists(path):
                            os.remove(path)

                asyncio.create_task(_background_human_service(temp_media_path))
                temp_media_path = None
                return {
                    "status": "success",
                    "mode": "human",
                    "accepted": True,
                    "user_text": "",
                    "detected_lang": "zh",
                    "raw_detected_lang": "",
                    "emotion": "背景分析中",
                    "customer_reply": "已通知客服人員，請稍候。",
                    "staff_summary": "已收到客服請求，後台會自動更新語音文字與情緒證據。",
                    "priority": "normal",
                    "customer_service_state": "pending",
                    "customer_service_priority": "normal",
                    "needs_human_staff": True,
                    "service_state_evidence": ["真人客服模式立即回傳"],
                    "emotion_structured": {},
                    "mentioned_ids": [],
                    "ollama_result": "",
                    "rag_doc_id": "",
                    "media_url": "",
                    "audio_base64": "",
                }
            return await customer_service_handler.handle_customer_service(
                session_id=session_id,
                media_path=temp_media_path,
                suffix=suffix,
                multi_lang=multi_lang_bool,
                use_ollama=use_ollama_bool,
                deps=deps,
            )
        except Exception as e:
            print(f"❌ customer_service 錯誤: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if temp_media_path and os.path.exists(temp_media_path):
                os.remove(temp_media_path)

    return router
