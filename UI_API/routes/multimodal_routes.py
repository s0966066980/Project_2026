import asyncio
import json
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

import ai_services
from repositories import interaction_event_repository
from realtime import event_bus
from services import barrier_state_service
from services import customer_service as customer_emotion_service
from services import interaction_event_service
from services import intervention_service
from services import multimodal_evidence_service
from utils.file_utils import write_binary_file


def _loads_dict(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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
                await event_bus.publish_to_admin("emotion_analysis_completed", {
                    "session_id": session_id,
                    "status": "skipped",
                    "message": "multimodal video chunk too small",
                })
                return {
                    "status": "skipped",
                    "message": "multimodal video chunk too small",
                }
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_video_path = tmp.name
            await asyncio.to_thread(write_binary_file, temp_video_path, video_bytes)

            media_signals = await ai_services.async_analyze_emotion_media_signals(temp_video_path)
            person_check = await customer_emotion_service.detect_person_for_emotion(
                temp_video_path, deps.get("yolo_semaphore")
            )
            if str(detect_only).lower() == "true":
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

            stt_result = await ai_services.async_safe_transcribe_with_language(temp_video_path)
            speech_text = (stt_result.get("text") or "").strip()

            async with deps["emotion_semaphore"]:
                emotion_data = await ai_services.async_get_emotion_from_llama(
                    temp_video_path,
                    speech_text,
                    media_signals,
                    interaction_context=interaction_context,
                    ui_context=ui_context,
                    risk_result=risk_result,
                )
            raw_emotion = emotion_data.get("emotion_raw", "") or "無法辨識具體情緒。"
            emotion_available = emotion_data.get("emotion_available", True)
            emotion_error = emotion_data.get("emotion_error", "")
            emotion_structured = await customer_emotion_service.emotion_to_structured_display(
                raw_emotion,
                person_check,
                speech_text,
                media_signals,
                deps.get("ollama_semaphore"),
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
            barrier_result = barrier_state_service.infer_barrier_state(
                emotion_structured=emotion_structured,
                speech_text=speech_text,
                pos_events=recent_events,
                ui_context=ui_context,
                media_signals=media_signals,
                risk_result=risk_result,
            )
            intervention = intervention_service.decide_intervention(barrier_result, ui_context)
            should_log = (
                intervention.get("action") != "none"
                and barrier_result.get("barrier_state") != "normal_operation"
            )
            intervention_log = None
            if should_log:
                log_payload = intervention_service.build_intervention_log(
                    session_id, barrier_result, intervention, ui_context
                )
                log_payload["multimodal_evidence"] = multimodal_evidence
                intervention_log = await asyncio.to_thread(
                    interaction_event_repository.append_intervention_log, log_payload
                )

            response_data = {
                "status": "success",
                "speech_text": speech_text[:120],
                "emotion_available": emotion_available,
                "emotion_error": emotion_error,
                "emotion_structured": emotion_structured,
                "multimodal_evidence": multimodal_evidence,
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
            if intervention.get("action") != "none":
                await event_bus.publish_intervention(session_id, {
                    "barrier_result": barrier_result,
                    "intervention": intervention,
                    "multimodal_evidence": multimodal_evidence,
                    "risk_result": risk_result,
                    "intervention_log": intervention_log,
                    "source": "triggered_multimodal_analysis",
                })
            if intervention.get("staff_notify"):
                await event_bus.publish_to_admin("staff_notify", {
                    "session_id": session_id,
                    "reason": intervention.get("reason", ""),
                    "barrier_state": barrier_result.get("barrier_state"),
                    "action": intervention.get("action"),
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
