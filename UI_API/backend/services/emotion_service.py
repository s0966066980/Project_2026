"""Emotion-LLaMA 情緒分析服務。

事件驅動：事件觸發時呼叫 analyze_event()，直接 in-process 呼叫推論函式，結果寫入 log。
語音快取：analyze_event 結果存入 session 快取，下一輪語音可讀取。
"""
import asyncio
import json
import os
import sys
import threading
from datetime import datetime

import config
from repositories import emotion_log_repository

_EMOTION_LLAMA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "Emotion-LLaMA")
)

EVENT_TYPE_LABELS = {
    "tutorial_popup": "如何點餐彈跳視窗",
}

_voice_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def is_enabled() -> bool:
    return bool(config.get("EMOTION_LLAMA_ENABLED", False))


def get_voice_emotion_cache(session_id: str) -> dict | None:
    with _cache_lock:
        return _voice_cache.get(session_id)


def clear_voice_emotion_cache(session_id: str) -> None:
    with _cache_lock:
        _voice_cache.pop(session_id, None)


async def analyze(session_id: str, media_path: str) -> dict:
    """emotion_routes 通用入口（保持向下相容）。"""
    return {
        "session_id": session_id,
        "emotion_label": "未偵測",
        "emotion_score": 0,
        "emotion_available": False,
        "status": "stub",
    }


async def analyze_event(session_id: str, media_path: str, event_type: str) -> dict:
    """事件驅動分析主入口。非同步執行，結果寫 log + 更新語音快取。"""
    if not is_enabled():
        return {"status": "disabled"}

    skip_qc = not bool(config.get("EMOTION_LLAMA_QUALITY_CHECK", True))
    prompt_template = config.get("EMOTION_LLAMA_PROMPT", "")
    question = prompt_template.replace("{speech_text}", "")

    try:
        raw = await _call_direct(media_path, question, skip_quality_check=skip_qc)
    except Exception as e:
        print(f"⚠️ Emotion-LLaMA analyze_event 失敗: {e}")
        return {"status": "error", "message": str(e)}

    quality_skipped = isinstance(raw, str) and raw.startswith("[EMOTION_LLAMA_SKIP]")
    error = isinstance(raw, str) and raw.startswith("[EMOTION_LLAMA_ERROR]")

    if isinstance(raw, str):
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"emotion": "", "description": raw, "facial": "", "body": "", "vocal": "", "intensity": ""}
    else:
        result = raw

    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "event_type": event_type,
        "event_type_label": EVENT_TYPE_LABELS.get(event_type, event_type),
        "clip_sec": float(config.get("EMOTION_LLAMA_CLIP_SEC", 2.0)),
        "quality_skipped": quality_skipped,
        "emotion": result.get("emotion", ""),
        "intensity": result.get("intensity", ""),
        "facial": result.get("facial", ""),
        "vocal": result.get("vocal", ""),
        "description": result.get("description", ""),
        "status": "skipped" if quality_skipped else ("error" if error else "ok"),
    }

    emotion_log_repository.append_log(entry)

    if not quality_skipped and not error and entry.get("emotion"):
        with _cache_lock:
            _voice_cache[session_id] = entry
        if config.get("EMOTION_LLAMA_AFFECT_BARRIER", False):
            try:
                asyncio.create_task(_trigger_barrier_update(session_id, entry))
            except RuntimeError:
                pass

    return entry


async def _trigger_barrier_update(session_id: str, emotion_entry: dict) -> None:
    """情緒結果非同步觸發 barrier_state 更新。"""
    try:
        from services import intervention_pipeline_service
        emotion_hint = {
            "emotion": emotion_entry.get("emotion", ""),
            "intensity": emotion_entry.get("intensity", ""),
            "event_type": emotion_entry.get("event_type", ""),
        }
        await intervention_pipeline_service.run_intervention_pipeline(
            session_id=session_id,
            ui_context={"emotion_hint": emotion_hint},
            speech_text="",
            source="emotion_llama",
        )
    except Exception as e:
        print(f"⚠️ Emotion barrier update 失敗: {e}")


async def _call_direct(video_path: str, question: str, skip_quality_check: bool = False) -> str:
    if _EMOTION_LLAMA_DIR not in sys.path:
        sys.path.insert(0, _EMOTION_LLAMA_DIR)
    from app_EmotionLlamaClient import process_video_question  # noqa: PLC0415
    return await asyncio.to_thread(process_video_question, video_path, question, skip_quality_check)
