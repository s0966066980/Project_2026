"""語音服務：STT → Ollama → TTS。

STT 和 TTS 實作透過 Provider 抽象層決定，不在此層關心。
"""
import asyncio
import base64
import json as _json
import re
import threading
import time
from typing import AsyncGenerator

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from services import (
    rag_guard_service,
    rag_offer_service,
    recommendation_context_service,
    recommendation_engine_service,
)
from services.recommendation_service import coerce_cart_actions
from services.stt_service import get_stt
from services.tts_service import get_tts

_menu_cache: dict = {"items": None, "context": None, "ts": 0.0}
_menu_cache_lock = asyncio.Lock()


async def _load_menu_cached() -> tuple:
    now = time.monotonic()
    ttl = float(config.get("VOICE_MENU_CACHE_TTL_SEC", 60.0))
    if _menu_cache["items"] is not None and now - _menu_cache["ts"] <= ttl:
        return _menu_cache["items"], _menu_cache["context"]
    async with _menu_cache_lock:
        now = time.monotonic()
        if _menu_cache["items"] is not None and now - _menu_cache["ts"] <= ttl:
            return _menu_cache["items"], _menu_cache["context"]
        items, context = await asyncio.gather(
            asyncio.to_thread(menu_repository.get_menu),
            asyncio.to_thread(database.build_compact_menu_context),
        )
        _menu_cache["items"] = items
        _menu_cache["context"] = context
        _menu_cache["ts"] = now
    return _menu_cache["items"], _menu_cache["context"]


def _format_history(history: list) -> str:
    if not history:
        return ""
    max_turns = int(config.get("VOICE_HISTORY_MAX_TURNS", 4))
    recent = history[-max_turns:]
    lines = []
    for turn in recent:
        if turn.get("user_speech"):
            lines.append(f"顧客：{turn['user_speech']}")
        if turn.get("ai_response"):
            ai_line = f"系統：{turn['ai_response']}"
            # 補上推薦 ID，讓下一輪 Ollama 可直接引用而不需在文字中重新解析
            ids = [i for i in (turn.get("mentioned_ids") or []) if i]
            if ids:
                ai_line += f"（推薦品項 ID：{', '.join(ids)}）"
            lines.append(ai_line)
    if not lines:
        return ""
    return "【對話歷史（最近幾輪）】\n" + "\n".join(lines)



def _build_emotion_context(session_id: str) -> str:
    """從語音情緒快取組出 prompt context 段落。
    只注入結構化欄位（emotion/intensity/facial/vocal）；
    原始英文 description 不注入，避免中英混雜干擾 Ollama 的對話記憶與購物車推斷。
    """
    if not config.get("EMOTION_LLAMA_AFFECT_VOICE", False):
        return ""
    from services.emotion_service import get_voice_emotion_cache
    cached = get_voice_emotion_cache(session_id)
    if not cached or not cached.get("emotion"):
        return ""
    parts = [f"情緒：{cached['emotion']}"]
    if cached.get("intensity"):
        parts.append(f"強度：{cached['intensity']}")
    if cached.get("facial"):
        parts.append(f"表情：{cached['facial']}")
    if cached.get("vocal"):
        parts.append(f"語調：{cached['vocal']}")
    return "【顧客情緒參考（Emotion-LLaMA）】\n" + "　".join(parts)


async def _build_voice_context(
    session_id: str,
    user_text: str,
    detected_lang: str,
) -> tuple[str, str, list]:
    """組合語音 LLM 的 system_prompt 與 user_prompt。

    handle_voice 與 handle_voice_stream 共用此邏輯：
    載入菜單與對話歷史、選定中／英 system prompt、注入情緒／RAG／熱門 context。
    回傳 (system_prompt, user_prompt, menu_items)。
    """
    (menu_items, full_menu_context), history = await asyncio.gather(
        _load_menu_cached(),
        asyncio.to_thread(session_repository.get_session_history, session_id),
    )
    history_context = _format_history(history)

    system_prompt = config.get(
        "VOICE_ASSIST_SYSTEM_PROMPT_EN" if detected_lang == "en" else "VOICE_ASSIST_SYSTEM_PROMPT"
    )

    # Emotion-LLaMA 快取注入（若啟用且有快取）
    emotion_context = _build_emotion_context(session_id)
    if emotion_context:
        system_prompt += (
            "\n若有顧客情緒參考，請據此調整語氣與推薦措辭。"
            "若顧客主動詢問情緒或心情相關問題，可自然地根據參考資料回應"
            "（例如「您看起來心情有些低落」），但不要說「我在分析情緒」或「系統偵測到」等字眼。"
        )

    recommendation_context = await recommendation_context_service.build_context(
        session_id,
        rag_query=user_text,
        surface="voice",
        menu_items=menu_items,
    )
    rag_context = recommendation_context.get("rag", {}).get("context", "")
    offer_section = rag_offer_service.format_offer_prompt_section(
        recommendation_context.get("rag", {}).get("offers") or [],
        audience=recommendation_context.get("audience", "guest"),
    )
    rag_guard_section = rag_guard_service.build_voice_guard_section(
        user_text,
        offers=recommendation_context.get("rag", {}).get("offers") or [],
        audience=recommendation_context.get("audience", "guest"),
        rag_context=rag_context,
    )
    member_section = recommendation_context_service.member_prompt_section(recommendation_context)
    recommendation = await asyncio.to_thread(
        recommendation_engine_service.recommend,
        recommendation_context,
        3,
        False,
    )
    recommendation_section = recommendation_engine_service.format_voice_recommendation_context(recommendation)

    input_label = "【本輪語音輸入】" if history_context else "【顧客語音輸入】"
    user_prompt = (
        (f"{history_context}\n\n" if history_context else "")
        + f"{input_label}\n{user_text}\n\n"
        + (f"{member_section}\n\n" if member_section else "")
        + (f"{emotion_context}\n\n" if emotion_context else "")
        + (f"{rag_guard_section}\n\n" if rag_guard_section else "")
        + (f"{offer_section}\n\n" if offer_section else "")
        + (f"{recommendation_section}\n\n" if recommendation_section else "")
        + (f"{rag_context}\n\n" if rag_context else "")
        + full_menu_context
    )
    return system_prompt, user_prompt, menu_items


async def handle_voice(
    session_id: str,
    audio_path: str,
    ollama_semaphore,
    multi_lang: bool = True,
) -> dict:
    # ── 1. STT ────────────────────────────────────────────────────
    stt = get_stt()
    try:
        stt_result = await stt.transcribe(audio_path)
    except Exception as e:
        return {
            "status": "error",
            "message": f"STT 失敗: {e}",
            "user_text": "", "ai_response": "", "audio_base64": "",
            "audio_format": "", "cart_actions": [], "detected_lang": "zh",
        }

    user_text = (stt_result.get("text") or "").strip()
    detected_lang = stt_result.get("language", "zh") if multi_lang else "zh"

    if not user_text:
        return {
            "status": "error",
            "message": "無法辨識語音內容",
            "user_text": "", "ai_response": "", "audio_base64": "",
            "audio_format": "", "cart_actions": [], "detected_lang": detected_lang,
        }

    # ── 2. Ollama LLM ─────────────────────────────────────────────
    system_prompt, user_prompt, menu_items = await _build_voice_context(
        session_id, user_text, detected_lang
    )

    model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
    async with ollama_semaphore:
        result = await asyncio.to_thread(
            ai_services.ask_ollama, system_prompt, user_prompt, "", model
        )

    if not isinstance(result, dict) or not result.get("ai_response"):
        ai_response = (
            "I can help with menu questions or add items to your cart."
            if detected_lang == "en"
            else "我可以協助您了解菜單或加入餐點。"
        )
        cart_actions = []
    else:
        ai_response = str(result.get("ai_response") or "").strip()
        raw_cart = result.get("cart_actions") or []
        cart_actions = coerce_cart_actions(
            raw_cart if isinstance(raw_cart, list) else [],
            user_text, menu_items,
        )
        if not ai_response:
            ai_response = "已為您加入購物車。" if cart_actions else "我可以協助您了解菜單或加入餐點。"

    _mentioned = result.get("mentioned_ids") or [] if isinstance(result, dict) else []
    await asyncio.to_thread(
        session_repository.record_session_state,
        session_id=session_id,
        user_speech=user_text,
        ai_response=ai_response,
        language=detected_lang,
        mentioned_ids=_mentioned,
        cart_actions=cart_actions,
    )

    # ── 3. TTS ────────────────────────────────────────────────────
    tts = get_tts()
    try:
        audio_base64 = await tts.synthesize_base64(ai_response, detected_lang)
    except Exception as e:
        print(f"⚠️ TTS 失敗: {e}")
        audio_base64 = ""

    return {
        "status": "success",
        "user_text": user_text,
        "ai_response": ai_response,
        "audio_base64": audio_base64,
        "audio_format": tts.audio_format,
        "cart_actions": cart_actions,
        "detected_lang": detected_lang,
    }


# ── 串流版語音處理 ─────────────────────────────────────────────────
_AI_RESP_RE = re.compile(r'"ai_response"\s*:\s*"((?:[^"\\]|\\.)*)')
_HARD_ENDS  = frozenset("。！？")
_SOFT_ENDS  = frozenset("，；\n")
_SOFT_MIN   = 15          # 軟斷點最小字數


async def handle_voice_stream(
    session_id: str,
    audio_path: str,
    ollama_semaphore,
    multi_lang: bool = True,
) -> AsyncGenerator[bytes, None]:
    """
    串流版：STT → LLM 串流 → 逐句 TTS。
    每個 chunk 為 NDJSON 行（後接 \\n）：
      {"type":"audio","data":"<base64>","format":"<wav|mp3>"}
      {"type":"done","status":"success","user_text":...,"ai_response":...,"cart_actions":...,"detected_lang":...}
    """
    tts = get_tts()
    stt = get_stt()

    # ── STT ──────────────────────────────────────────────────────────
    try:
        stt_result = await stt.transcribe(audio_path)
    except Exception as e:
        err = _json.dumps({"type": "done", "status": "error", "message": f"STT 失敗: {e}"})
        yield (err + "\n").encode()
        return

    user_text    = (stt_result.get("text") or "").strip()
    detected_lang = stt_result.get("language", "zh") if multi_lang else "zh"

    if not user_text:
        err = _json.dumps({"type": "done", "status": "error", "message": "無法辨識語音內容"})
        yield (err + "\n").encode()
        return

    # ── Context + System prompt（與 handle_voice 共用組裝邏輯） ──────────
    system_prompt, user_prompt, menu_items = await _build_voice_context(
        session_id, user_text, detected_lang
    )

    model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
    voice_num_predict = int(config.get("VOICE_NUM_PREDICT",
                            config.get("OLLAMA_NUM_PREDICT", 220)))

    # ── LLM 串流 → 逐句 TTS ─────────────────────────────────────────
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _run_stream():
        try:
            for token in ai_services.stream_ollama_tokens(system_prompt, user_prompt, model, voice_num_predict):
                loop.call_soon_threadsafe(queue.put_nowait, token)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    full_buf   = ""   # 累積完整 token 串，最後解析 JSON
    matched_len = 0   # 已處理 ai_response 長度
    sent_buf   = ""   # 待 TTS 的句子 buffer
    ai_response_final = ""

    async with ollama_semaphore:
        threading.Thread(target=_run_stream, daemon=True).start()

        while True:
            token = await queue.get()
            if token is None:
                break
            full_buf += token

            m = _AI_RESP_RE.search(full_buf)
            if not m:
                continue

            new_text = m.group(1)[matched_len:]
            matched_len = len(m.group(1))
            sent_buf += new_text

            # 找斷點
            flush_at = -1
            for i, ch in enumerate(sent_buf):
                if ch in _HARD_ENDS:
                    flush_at = i
                    break
                if ch in _SOFT_ENDS and i >= _SOFT_MIN:
                    flush_at = i
                    break

            if flush_at >= 0:
                sentence = sent_buf[:flush_at + 1].strip()
                sent_buf = sent_buf[flush_at + 1:]
                if sentence:
                    try:
                        audio_bytes = await tts.synthesize(sentence, detected_lang)
                        b64 = base64.b64encode(audio_bytes).decode()
                        chunk = _json.dumps({
                            "type": "audio",
                            "data": b64,
                            "format": tts.audio_format,
                        }, ensure_ascii=False)
                        yield (chunk + "\n").encode()
                    except Exception as e:
                        print(f"⚠️ 串流 TTS 失敗: {e}")

    # 剩餘 buffer flush
    remainder = sent_buf.strip()
    if remainder:
        try:
            audio_bytes = await tts.synthesize(remainder, detected_lang)
            b64 = base64.b64encode(audio_bytes).decode()
            chunk = _json.dumps({
                "type": "audio",
                "data": b64,
                "format": tts.audio_format,
            }, ensure_ascii=False)
            yield (chunk + "\n").encode()
        except Exception:
            pass

    # 解析完整 JSON → cart_actions
    result = ai_services.parse_llm_json(full_buf, "VOICE_STREAM")
    ai_response_final = str(result.get("ai_response") or "").strip() or remainder
    raw_cart    = result.get("cart_actions") or []
    cart_actions = coerce_cart_actions(
        raw_cart if isinstance(raw_cart, list) else [],
        user_text, menu_items,
    )
    mentioned_ids = result.get("mentioned_ids") or []

    # 寫回 session history（含推薦 ID，供下一輪多輪記憶使用）
    await asyncio.to_thread(
        session_repository.record_session_state,
        session_id=session_id,
        user_speech=user_text,
        ai_response=ai_response_final,
        language=detected_lang,
        mentioned_ids=mentioned_ids,
        cart_actions=cart_actions,
    )

    done = _json.dumps({
        "type": "done",
        "status": "success",
        "user_text": user_text,
        "ai_response": ai_response_final,
        "cart_actions": cart_actions,
        "mentioned_ids": mentioned_ids,
        "detected_lang": detected_lang,
    }, ensure_ascii=False)
    yield (done + "\n").encode()
