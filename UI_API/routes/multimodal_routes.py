import asyncio
import json
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

import ai_services
from repositories import emotion_clip_repository, interaction_event_repository
from realtime import event_bus
from services import customer_service as customer_emotion_service
from services import interaction_event_service
from services import intervention_pipeline_service
from services import multimodal_evidence_service
from utils.file_utils import write_binary_file


def _loads_dict(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _publish_fallback_intervention(session_id: str, risk_result: dict, ui_context: dict, recent_events: list, message: str):
    media_signals = {"reason": message, "audio_silent": True, "motion_level": "unknown"}
    pipeline_result = await intervention_pipeline_service.run_intervention_pipeline(
        session_id=session_id,
        ui_context=ui_context,
        risk_result=risk_result,
        recent_events=recent_events,
        speech_text="",
        emotion_structured={},
        media_signals=media_signals,
        multimodal_evidence={
            "visual_evidence": {"person_detected": None, "reason": message},
            "audio_evidence": {"speech_text": "", "audio_silent": True},
            "emotion_evidence": {
                "emotion_available": False,
                "emotion_error": message,
                "model_source": "Emotion-LLaMA",
            },
            "pos_evidence": {
                "page_id": ui_context.get("page_id"),
                "risk_score": risk_result.get("risk_score"),
                "trigger_reasons": risk_result.get("trigger_reasons", []),
            },
        },
        source="triggered_multimodal_analysis_fallback",
    )
    return (
        pipeline_result.get("barrier_result"),
        pipeline_result.get("intervention"),
        pipeline_result.get("intervention_log"),
    )


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["multimodal"])

    @router.post("/triggered_multimodal_analysis")
    async def triggered_multimodal_analysis(
        session_id: str = Form(...),
        video: UploadFile = File(...),
        risk_result_json: str = Form(default="{}"),
        ui_context_json: str = Form(default="{}"),
        interaction_context: str = Form(default=""),
        detect_only: str = Form(default="false"),
    ):
        temp_video_path = None
        try:
            risk_result = _loads_dict(risk_result_json)
            ui_context = _loads_dict(ui_context_json)
            await event_bus.publish_to_admin("emotion_analysis_started", {
                "session_id": session_id,
                "page_id": ui_context.get("page_id"),
                "risk_result": risk_result,
            })
            recent_events = await asyncio.to_thread(
                interaction_event_repository.get_recent_session_events, session_id
            )
            if not risk_result:
                risk_result = interaction_event_service.calculate_interaction_risk(
                    recent_events, ui_context
                )
            if not interaction_context:
                interaction_context = interaction_event_service.build_interaction_context(
                    recent_events, risk_result
                )

            suffix = os.path.splitext(video.filename or ".webm")[1] or ".webm"
            video_bytes = await video.read()
            if len(video_bytes) < 2000:
                message = "multimodal video chunk too small"
                barrier_result, intervention, intervention_log = await _publish_fallback_intervention(
                    session_id, risk_result, ui_context, recent_events, message
                )
                await event_bus.publish_to_admin("emotion_analysis_completed", {
                    "session_id": session_id,
                    "status": "success",
                    "multimodal_skipped": True,
                    "message": message,
                    "barrier_result": barrier_result,
                    "intervention": intervention,
                })
                return {
                    "status": "success",
                    "multimodal_skipped": True,
                    "message": message,
                    "speech_text": "",
                    "emotion_available": False,
                    "emotion_error": message,
                    "emotion_structured": {},
                    "multimodal_evidence": {},
                    "risk_result": risk_result,
                    "barrier_result": barrier_result,
                    "intervention": intervention,
                    "intervention_log": intervention_log,
                }
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_video_path = tmp.name
            await asyncio.to_thread(write_binary_file, temp_video_path, video_bytes)
            media_probe = await ai_services.async_probe_media(temp_video_path)
            if not media_probe.get("valid") or not media_probe.get("has_video"):
                message = f"multimodal video unreadable: {media_probe.get('error') or 'no_video'}"
                barrier_result, intervention, intervention_log = await _publish_fallback_intervention(
                    session_id, risk_result, ui_context, recent_events, message
                )
                await event_bus.publish_to_admin("emotion_analysis_completed", {
                    "session_id": session_id,
                    "status": "skipped",
                    "message": message,
                    "barrier_result": barrier_result,
                    "intervention": intervention,
                })
                return {
                    "status": "success",
                    "multimodal_skipped": True,
                    "message": message,
                    "speech_text": "",
                    "emotion_available": False,
                    "emotion_error": message,
                    "emotion_structured": {},
                    "multimodal_evidence": {},
                    "risk_result": risk_result,
                    "barrier_result": barrier_result,
                    "intervention": intervention,
                    "intervention_log": intervention_log,
                }

            if str(detect_only).lower() == "true":
                media_signals, person_check = await asyncio.gather(
                    ai_services.async_analyze_emotion_media_signals(temp_video_path),
                    customer_emotion_service.detect_person_for_emotion(
                        temp_video_path, deps.get("yolo_semaphore")
                    ),
                )
                await event_bus.publish_to_admin("emotion_analysis_completed", {
                    "session_id": session_id,
                    "status": "success",
                    "detect_only": True,
                    "person_check": person_check,
                    "media_signals": media_signals,
                })
                return {
                    "status": "success",
                    "person_check": person_check,
                    "media_signals": media_signals,
                    "detect_only": True,
                }

            media_signals, person_check, stt_result = await asyncio.gather(
                ai_services.async_analyze_emotion_media_signals(temp_video_path),
                customer_emotion_service.detect_person_for_emotion(
                    temp_video_path, deps.get("yolo_semaphore")
                ),
                ai_services.async_safe_transcribe_with_language(temp_video_path),
            )
            speech_text = (stt_result.get("text") or "").strip()

            # Emotion-LLaMA is reserved for customer-service mode only (2-5).
            # General event-triggered pipeline uses YOLO + Whisper only.
            raw_emotion = "未啟用"
            emotion_available = False
            emotion_error = "Emotion-LLaMA 已停用（僅在客服模式啟用）"
            emotion_structured = customer_emotion_service.build_emotion_structured(
                raw_emotion,
                "Emotion-LLaMA 未執行：保留給客服模式使用。",
                "無法判斷",
                evidence_hint=emotion_error,
                person_check=person_check,
                speech_text=speech_text,
                media_signals=media_signals,
            )
            multimodal_evidence = multimodal_evidence_service.build_multimodal_evidence(
                emotion_structured=emotion_structured,
                person_check=person_check,
                media_signals=media_signals,
                speech_text=speech_text,
                risk_result=risk_result,
                ui_context=ui_context,
                interaction_context=interaction_context,
                emotion_available=emotion_available,
                emotion_error=emotion_error,
            )
            display_emotion = emotion_structured.get("emotion_display") or emotion_structured.get("emotion_label") or raw_emotion
            no_person = bool(
                person_check.get("available")
                and person_check.get("person_detected") is False
            )
            clip = await asyncio.to_thread(
                emotion_clip_repository.save_clip,
                session_id,
                temp_video_path,
                raw_emotion,
                display_emotion,
                person_check,
                no_person,
                emotion_structured,
                media_signals,
                True,
            )
            deps["emotion_cache"][session_id] = {
                "emotion": raw_emotion,
                "emotion_display": display_emotion,
                "emotion_structured": emotion_structured,
                "person_check": person_check,
                "media_signals": media_signals,
                "clip": clip,
            }
            pipeline_result = await intervention_pipeline_service.run_intervention_pipeline(
                session_id=session_id,
                ui_context=ui_context,
                risk_result=risk_result,
                recent_events=recent_events,
                speech_text=speech_text,
                emotion_structured=emotion_structured,
                media_signals=media_signals,
                person_check=person_check,
                multimodal_evidence=multimodal_evidence,
                source="triggered_multimodal_analysis",
            )
            barrier_result = pipeline_result.get("barrier_result")
            intervention = pipeline_result.get("intervention")
            intervention_log = pipeline_result.get("intervention_log")

            response_data = {
                "status": "success",
                "speech_text": speech_text[:120],
                "emotion_available": emotion_available,
                "emotion_error": emotion_error,
                "emotion_structured": emotion_structured,
                "multimodal_evidence": multimodal_evidence,
                "clip": clip,
                "risk_result": risk_result,
                "barrier_result": barrier_result,
                "intervention": intervention,
                "intervention_log": intervention_log,
            }
            await event_bus.publish_to_admin("emotion_analysis_completed", {
                "session_id": session_id,
                "status": "success",
                "risk_result": risk_result,
                "barrier_result": barrier_result,
                "intervention": intervention,
                "emotion_available": emotion_available,
                "emotion_error": emotion_error,
            })
            return response_data
        except Exception as e:
            await event_bus.publish_to_admin("emotion_analysis_completed", {
                "session_id": session_id,
                "status": "error",
                "message": str(e),
            })
            return {"status": "error", "message": str(e)}
        finally:
            if temp_video_path and os.path.exists(temp_video_path):
                try:
                    await asyncio.to_thread(os.remove, temp_video_path)
                except OSError:
                    pass

    return router
