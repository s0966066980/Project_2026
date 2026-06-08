"""Emotion-LLaMA 情緒分析服務。

事件驅動：事件觸發時呼叫 analyze_event()，HTTP 呼叫獨立 FastAPI server（port 7889），結果寫入 log。
語音快取：analyze_event 結果存入 session 快取，下一輪語音可讀取。
"""
import asyncio
import json
import re
import threading
from datetime import datetime

import httpx

import ai_services
import config
from repositories import emotion_log_repository

EVENT_TYPE_LABELS = {
    "tutorial_popup": "如何點餐彈跳視窗",
    "voice_mode": "語音模式",
    "cancel_guide": "需要幫助彈跳視窗",
    "payment_timeout": "付款逾時協助",
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


async def analyze_event(session_id: str, media_path: str, event_type: str, speech_text: str = "") -> dict:
    """事件驅動分析主入口。非同步執行，結果寫 log + 更新語音快取。"""
    if not is_enabled():
        return {"status": "disabled"}

    skip_qc = not bool(config.get("EMOTION_LLAMA_QUALITY_CHECK", True))
    prompt_template = config.get("EMOTION_LLAMA_PROMPT", "")
    if speech_text and speech_text.strip():
        question = prompt_template.replace("{speech_text}", speech_text)
    else:
        # 無語音時移除含 {speech_text} 的整行，避免模型看到空白語句
        question = re.sub(r"[^\n]*\{speech_text\}[^\n]*\n?", "", prompt_template).strip()
        if not question:
            question = prompt_template.replace("{speech_text}", "(no speech)")

    try:
        raw = await _call_http(media_path, question, skip_quality_check=skip_qc)
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

    # Emotion-LLaMA 常輸出自然語言而非結構化欄位；同步呼叫 Ollama 補全
    # （frontend 對 analyze_event 是 fire-and-forget，此處等待不影響 UI）
    if (not quality_skipped and not error
            and not result.get("emotion")
            and result.get("description")):
        try:
            ollama_fields = await _extract_emotion_via_ollama(result["description"])
            if ollama_fields.get("emotion"):
                result["emotion"]   = ollama_fields.get("emotion",   "")
                result["intensity"] = ollama_fields.get("intensity", "") or result.get("intensity", "")
                result["facial"]    = ollama_fields.get("facial",    "") or result.get("facial",    "")
                result["vocal"]     = ollama_fields.get("vocal",     "") or result.get("vocal",     "")
        except Exception as e:
            print(f"⚠️ Emotion Ollama 提取失敗: {e}")

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

    # 付款逾時事件：情緒分析成功後，用 Ollama 生成協助語供前端「人員協助付款」顯示
    if (event_type == "payment_timeout"
            and not quality_skipped and not error
            and entry.get("emotion")):
        try:
            entry["assist_response"] = await _generate_payment_assist(entry)
        except Exception as e:
            print(f"⚠️ Payment assist Ollama 生成失敗: {e}")

    emotion_log_repository.append_log(entry)
    _print_entry(entry)

    if not quality_skipped and not error and entry.get("emotion"):
        with _cache_lock:
            _voice_cache[session_id] = entry
        if config.get("EMOTION_LLAMA_AFFECT_BARRIER", False):
            try:
                asyncio.create_task(_trigger_barrier_update(session_id, entry))
            except RuntimeError:
                pass

    return entry


def _print_entry(entry: dict) -> None:
    sid   = entry.get("session_id", "?")[:8]
    evt   = entry.get("event_type_label") or entry.get("event_type", "")
    st    = entry.get("status", "")
    if st == "skipped":
        print(f"[Emotion] {sid} | {evt} | 品質快篩跳過")
        return
    if st == "error":
        print(f"[Emotion] {sid} | {evt} | ⚠️ 分析失敗")
        return
    emo   = entry.get("emotion", "—")
    intens = entry.get("intensity", "")
    facial = entry.get("facial", "")
    vocal  = entry.get("vocal", "")
    desc   = entry.get("description", "")
    parts = [f"情緒={emo}"]
    if intens:
        parts.append(f"強度={intens}")
    if facial:
        parts.append(f"表情={facial}")
    if vocal:
        parts.append(f"聲音={vocal}")
    if desc:
        desc_display = desc[:120] + ("…" if len(desc) > 120 else "")
        parts.append(f"描述={desc_display}")
    print(f"[Emotion] {sid} | {evt} | " + " | ".join(parts))



async def _extract_emotion_via_ollama(description: str) -> dict:
    """Emotion-LLaMA 自然語言描述 → Ollama → 結構化情緒欄位。"""
    system = (
        "You are an emotion extraction assistant. "
        "Given a video analysis description, extract the structured emotion data. "
        "Reply ONLY with valid JSON, no extra text."
    )
    user = (
        f"Analysis description:\n{description}\n\n"
        "Return ONLY this JSON (fill in values based on the description):\n"
        '{"emotion":"<primary emotion label, e.g. neutral/happy/frustrated/anxious/sad>",'
        '"intensity":"low|medium|high",'
        '"facial":"<brief facial cues>",'
        '"vocal":"<brief vocal cues or silent>"}'
    )
    result = await asyncio.to_thread(
        ai_services.ask_ollama, system, user, "EMOTION_EXTRACT",
        config.get("MODEL_NAME", "qwen3.5:4b"),
        120,
    )
    return result if isinstance(result, dict) else {}


async def _generate_payment_assist(entry: dict) -> str:
    """付款逾時：依情緒分析生成一句溫暖協助語（供前端「人員協助付款」顯示）。"""
    system = config.get(
        "PAYMENT_ASSIST_PROMPT",
        "你是麥當勞自助點餐機的智能協助員。"
        "根據顧客的情緒分析，生成一句溫暖友善的協助語（繁體中文，20–40 字）。"
        "不要提及你在分析情緒或任何系統流程，用自然口語安慰付款遇到困難的顧客，"
        "並表示店員即將前來協助。"
        '只輸出 JSON：{"assist_message":"..."}',
    )
    user = (
        f"顧客情緒：{entry.get('emotion','')}（強度：{entry.get('intensity','')}）\n"
        f"表情：{entry.get('facial','')}\n"
        f"描述：{(entry.get('description','') or '')[:150]}\n"
        "請生成一句友善協助語。"
    )
    result = await asyncio.to_thread(
        ai_services.ask_ollama, system, user, "PAYMENT_ASSIST",
        config.get("MODEL_NAME", "qwen3.5:4b"), 80,
    )
    return str(result.get("assist_message") or "") if isinstance(result, dict) else ""


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


async def _call_http(video_path: str, question: str, skip_quality_check: bool = False) -> str:
    url = f"{config.EMOTION_LLAMA_GRADIO_URL}/predict"
    async with httpx.AsyncClient(timeout=float(config.get("EMOTION_LLAMA_TIMEOUT_SEC", 120))) as client:
        resp = await client.post(url, json={
            "video_path": video_path,
            "question": question,
            "skip_quality_check": skip_quality_check,
        })
        resp.raise_for_status()
        return resp.json()["result"]
