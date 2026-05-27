import asyncio
import os
import subprocess
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

_EMOTION_LLAMA_PROC: subprocess.Popen | None = None


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
            "gradio_url": config.EMOTION_LLAMA_GRADIO_URL,
            **status,
        }

    @router.post("/emotion_llama/start")
    async def start_emotion_llama(request: Request):
        """Start the independent Emotion-LLaMA client when voice assist needs emotion evidence."""
        require_admin_token(request)
        global _EMOTION_LLAMA_PROC

        # Already running?
        if _EMOTION_LLAMA_PROC is not None and _EMOTION_LLAMA_PROC.poll() is None:
            return {"status": "already_running", "pid": _EMOTION_LLAMA_PROC.pid}

        client_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "Emotion-LLaMA", "app_EmotionLlamaClient.py",
        )
        client_path = os.path.normpath(client_path)
        if not os.path.exists(client_path):
            return {"status": "error", "message": f"app_EmotionLlamaClient.py not found at {client_path}"}

        cmd = [
            "bash", "-c",
            f"source $(conda info --base)/etc/profile.d/conda.sh && "
            f"conda activate emotion_ollama && "
            f"python {client_path}",
        ]
        try:
            proc = await asyncio.to_thread(
                subprocess.Popen,
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            _EMOTION_LLAMA_PROC = proc
            return {"status": "success", "pid": proc.pid, "message": "Emotion-LLaMA 啟動中"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @router.post("/emotion_llama/stop")
    async def stop_emotion_llama(request: Request):
        """Stop the managed Emotion-LLaMA client process and release GPU/CPU resources."""
        require_admin_token(request)
        global _EMOTION_LLAMA_PROC
        proc = _EMOTION_LLAMA_PROC
        if proc is None or proc.poll() is not None:
            _EMOTION_LLAMA_PROC = None
            return {"status": "not_running"}
        try:
            proc.terminate()
            try:
                await asyncio.to_thread(proc.wait, timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                await asyncio.to_thread(proc.wait, timeout=5)
            pid = proc.pid
            _EMOTION_LLAMA_PROC = None
            return {"status": "success", "pid": pid, "message": "Emotion-LLaMA 已停止"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

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
            person_check = None

            if detect_only.lower() == "true":
                raw_emotion = "偵測完成"
                emotion_structured = customer_emotion_service.build_emotion_structured(
                    raw_emotion,
                    "媒體訊號分析完成。",
                    "無法判斷",
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
