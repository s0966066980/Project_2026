import asyncio
import os
import tempfile
import time

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

import ai_services
import config
from repositories import emotion_clip_repository, session_repository
from services import customer_service as customer_emotion_service
from utils.auth_utils import require_admin_token
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["emotion"])

    @router.get("/emotion_status")
    async def get_emotion_status(request: Request):
        require_admin_token(request)
        status = await asyncio.to_thread(ai_services.check_emotion_llama_status)
        return {
            "status": "success",
            "enabled": bool(config.get("EVENT_TRIGGERED_MULTIMODAL_ENABLED", True)),
            "periodic_enabled": bool(config.get("EMOTION_PERIODIC_ENABLED", False)),
            "influence_recommend": bool(config.get("EMOTION_INFLUENCE_RECOMMEND", True)),
            "gradio_url": config.EMOTION_LLAMA_GRADIO_URL,
            **status,
        }

    @router.get("/emotion_clips/{session_id}")
    async def get_emotion_clips(request: Request, session_id: str):
        require_admin_token(request)
        safe_session = emotion_clip_repository.safe_session_id(session_id)
        clips = await asyncio.to_thread(emotion_clip_repository.load_clip_index, safe_session)
        return {"status": "success", "session_id": safe_session, "clips": clips}

    @router.get("/emotion_clips/{session_id}/media/{clip_id}")
    async def get_emotion_clip_media(request: Request, session_id: str, clip_id: str):
        require_admin_token(request)
        safe_session = emotion_clip_repository.safe_session_id(session_id)
        safe_clip = emotion_clip_repository.safe_clip_id(clip_id)
        path = os.path.join(emotion_clip_repository.emotion_clip_dir(safe_session), safe_clip)
        if not os.path.exists(path):
            return {"status": "not_found"}
        return FileResponse(path, media_type="video/webm", filename=safe_clip)

    @router.delete("/emotion_clips/{session_id}")
    async def delete_emotion_clips(request: Request, session_id: str):
        require_admin_token(request)
        safe_session = emotion_clip_repository.safe_session_id(session_id)
        await asyncio.to_thread(emotion_clip_repository.delete_all_clips, safe_session)
        return {"status": "success", "session_id": safe_session}

    @router.post("/person_detect_frame")
    async def person_detect_frame(session_id: str = Form(...), frame: UploadFile = File(...)):
        if not config.get("EMOTION_PERSON_CHECK_ENABLED", True):
            return {
                "status": "disabled",
                "person_check": {"available": False, "person_detected": None, "reason": "disabled"},
            }
        if deps["yolo_semaphore"].locked():
            return {"status": "skipped", "message": "YOLO busy"}
        image_bytes = await frame.read()
        loop = asyncio.get_running_loop()
        async with deps["yolo_semaphore"]:
            person_check = await loop.run_in_executor(
                None, ai_services.detect_person_in_image_bytes, image_bytes
            )
        return {"status": "success", "session_id": emotion_clip_repository.safe_session_id(session_id), "person_check": person_check}

    def _build_emotion_response(
        session_id: str,
        raw_emotion: str,
        display_emotion: str,
        emotion_structured: dict,
        no_person: bool,
        person_check: dict | None,
        clip: dict | None = None,
        speech_text: str = "",
        detected_lang: str = "zh",
        extra: dict | None = None,
    ) -> dict:
        deps["emotion_cache"][session_id] = {
            "emotion": raw_emotion,
            "emotion_display": display_emotion,
            "emotion_structured": emotion_structured,
            "no_person": no_person,
            "person_check": person_check,
            "clip": clip,
            "ts": time.time(),
        }
        response = {
            "status": "success",
            "emotion": raw_emotion,
            "emotion_display": display_emotion,
            "emotion_structured": emotion_structured,
            "no_person": no_person,
            "person_check": person_check,
            "clip": clip,
        }
        if speech_text:
            response["speech_text"] = speech_text
            response["detected_lang"] = detected_lang
        if extra:
            response.update(extra)
        return response

    @router.post("/ping_state")
    async def process_ping_state(
        session_id: str = Form(...),
        video: UploadFile = File(...),
        detect_only: str = Form(default="false"),
    ):
        temp_video_path = None
        try:
            now = time.time()
            min_gap = float(config.get("EMOTION_MIN_GAP_SEC", 12))
            cached = deps["emotion_cache"].get(session_id)
            if cached and now - cached["ts"] < min_gap:
                return {
                    "status": "success",
                    "emotion": cached["emotion"],
                    "emotion_display": cached.get("emotion_display", cached["emotion"]),
                    "emotion_structured": cached.get("emotion_structured"),
                    "cached": True,
                    "no_person": cached.get("no_person", False),
                    "person_check": cached.get("person_check"),
                    "clip": cached.get("clip"),
                }

            if deps["emotion_semaphore"].locked():
                if cached:
                    return {
                        "status": "success",
                        "emotion": cached["emotion"],
                        "emotion_display": cached.get("emotion_display", cached["emotion"]),
                        "emotion_structured": cached.get("emotion_structured"),
                        "cached": True,
                        "busy": True,
                        "no_person": cached.get("no_person", False),
                        "person_check": cached.get("person_check"),
                        "clip": cached.get("clip"),
                    }
                return {"status": "skipped", "message": "Emotion-LLaMA busy"}

            suffix = os.path.splitext(video.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_video_path = tmp.name
            video_bytes = await video.read()
            if len(video_bytes) < 2000:
                return {"status": "skipped", "message": "emotion video chunk too small"}
            await asyncio.to_thread(write_binary_file, temp_video_path, video_bytes)

            media_signals = await ai_services.async_analyze_emotion_media_signals(temp_video_path)
            person_check = await customer_emotion_service.detect_person_for_emotion(
                temp_video_path, deps["yolo_semaphore"]
            )
            if (
                person_check.get("available")
                and person_check.get("person_detected") is False
                and media_signals.get("audio_silent", True)
            ):
                raw_emotion = "未偵測到顧客"
                emotion_structured = customer_emotion_service.build_emotion_structured(
                    raw_emotion, raw_emotion, "未偵測到顧客",
                    person_check=person_check, media_signals=media_signals,
                )
                display_emotion = emotion_structured["emotion_display"]
                clip = await asyncio.to_thread(
                    emotion_clip_repository.save_clip, session_id, temp_video_path, raw_emotion,
                    display_emotion, person_check, True, emotion_structured, media_signals,
                )
                session_repository.record_session_state(
                    session_id=session_id, emotion=display_emotion,
                    user_speech="", ai_response="",
                )
                return _build_emotion_response(
                    session_id, raw_emotion, display_emotion,
                    emotion_structured, True, person_check, clip,
                )

            if detect_only.lower() == "true":
                raw_emotion = "人物已偵測"
                emotion_structured = customer_emotion_service.build_emotion_structured(
                    raw_emotion,
                    "人物已偵測：鏡頭中有明確人物。",
                    "無法判斷",
                    person_check=person_check,
                    media_signals=media_signals,
                )
                display_emotion = emotion_structured["emotion_display"]
                clip = await asyncio.to_thread(
                    emotion_clip_repository.save_clip, session_id, temp_video_path, raw_emotion,
                    display_emotion, person_check, False, emotion_structured, media_signals,
                )
                return _build_emotion_response(
                    session_id, raw_emotion, display_emotion,
                    emotion_structured, False, person_check, clip,
                    extra={"detect_only": True},
                )

            stt_result = await ai_services.async_safe_transcribe_with_language(temp_video_path)
            speech_text = (stt_result.get("text") or "").strip()

            async with deps["emotion_semaphore"]:
                emotion_data = await ai_services.async_get_emotion_from_llama(
                    temp_video_path, speech_text, media_signals
                )
            raw_emotion = emotion_data["emotion_raw"]
            if emotion_data.get("emotion_available") is False:
                emotion_structured = customer_emotion_service.build_emotion_structured(
                    raw_emotion,
                    "Emotion-LLaMA 未執行：服務未連線或尚未啟動。",
                    "無法判斷",
                    evidence_hint="Emotion-LLaMA 服務未連線。",
                    person_check=person_check,
                    speech_text=speech_text,
                    media_signals=media_signals,
                )
                display_emotion = emotion_structured["emotion_display"]
                return _build_emotion_response(
                    session_id, raw_emotion, display_emotion,
                    emotion_structured, False, person_check, None,
                    speech_text=speech_text,
                    detected_lang=stt_result.get("language", "zh"),
                    extra={
                        "status": "not_executed",
                        "message": "Emotion-LLaMA 未執行",
                    },
                )
            emotion_structured = await customer_emotion_service.emotion_to_structured_display(
                raw_emotion, person_check, speech_text, media_signals, deps["ollama_semaphore"]
            )
            display_emotion = emotion_structured["emotion_display"]
            clip = await asyncio.to_thread(
                emotion_clip_repository.save_clip, session_id, temp_video_path, raw_emotion,
                display_emotion, person_check, False, emotion_structured, media_signals,
            )
            session_repository.record_session_state(
                session_id=session_id, emotion=display_emotion,
                user_speech=speech_text, ai_response="",
                language=stt_result.get("language", "zh"),
            )
            return _build_emotion_response(
                session_id, raw_emotion, display_emotion,
                emotion_structured, False, person_check, clip,
                speech_text=speech_text,
                detected_lang=stt_result.get("language", "zh"),
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_video_path and os.path.exists(temp_video_path):
                await asyncio.to_thread(os.remove, temp_video_path)

    return router
