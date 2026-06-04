"""語音服務：STT → Ollama → TTS。

STT 和 TTS 實作透過 Provider 抽象層決定，不在此層關心。
"""
import asyncio
import time

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from services.mood_service import get_mood_context
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
            asyncio.to_thread(database.build_full_menu_context),
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
            lines.append(f"系統：{turn['ai_response']}")
    if not lines:
        return ""
    return "【對話歷史（最近幾輪）】\n" + "\n".join(lines)



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
    (menu_items, full_menu_context), history = await asyncio.gather(
        _load_menu_cached(),
        asyncio.to_thread(session_repository.get_session_history, session_id),
    )
    history_context = _format_history(history)

    if detected_lang == "en":
        system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT_EN")
    else:
        system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT")

    # RAG context 注入
    if config.get("RAG_ENABLED", False):
        from services.rag_provider import get_rag
        rag_context = await get_rag().query(user_text)
    else:
        rag_context = ""

    # 注入心情 context（若顧客有選心情星星）
    mood_context = get_mood_context(session_id)
    if mood_context:
        system_prompt = f"【顧客心情參考】\n{mood_context}\n\n{system_prompt}"

    # Emotion-LLaMA 快取注入（若啟用且有快取）
    emotion_context = ""
    if config.get("EMOTION_LLAMA_AFFECT_VOICE", False):
        from services.emotion_service import get_voice_emotion_cache
        cached = get_voice_emotion_cache(session_id)
        if cached and cached.get("emotion"):
            parts = [f"情緒：{cached['emotion']}"]
            if cached.get("intensity"):
                parts.append(f"強度：{cached['intensity']}")
            if cached.get("facial"):
                parts.append(f"表情：{cached['facial']}")
            if cached.get("vocal"):
                parts.append(f"語調：{cached['vocal']}")
            emotion_context = "【顧客情緒參考（Emotion-LLaMA）】\n" + "　".join(parts)

    if emotion_context:
        system_prompt += "\n若有顧客情緒參考，請據此調整語氣，但不要直接提及你在分析情緒。"

    # 熱門點選 TOP 3（讓 LLM 回答一般推薦問題時有依據）
    from services.popular_service import get_top_items
    top_items = await asyncio.to_thread(get_top_items, 3)
    popular_section = ""
    if top_items:
        lines = "\n".join(
            f"{i+1}. {t['name']}（{t['id']}）" for i, t in enumerate(top_items)
        )
        popular_section = f"【熱門點選 TOP 3】\n{lines}\n\n"

    input_label = "【本輪語音輸入】" if history_context else "【顧客語音輸入】"
    user_prompt = (
        (f"{history_context}\n\n" if history_context else "")
        + f"{input_label}\n{user_text}\n\n"
        + (f"{emotion_context}\n\n" if emotion_context else "")
        + popular_section
        + (f"{rag_context}\n\n" if rag_context else "")
        + full_menu_context
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

    await asyncio.to_thread(
        session_repository.record_session_state,
        session_id=session_id,
        user_speech=user_text,
        ai_response=ai_response,
        language=detected_lang,
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
        "audio_format": tts.audio_format,   # "wav" 或 "mp3"，前端用此決定 MIME type
        "cart_actions": cart_actions,
        "detected_lang": detected_lang,
    }
