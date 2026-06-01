"""語音服務：STT → Ollama → TTS。

STT 和 TTS 實作透過 Provider 抽象層決定，不在此層關心。
"""
import asyncio

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from services.recommendation_service import coerce_cart_actions
from services.stt_service import get_stt
from services.tts_service import get_tts

_DEFAULT_SYSTEM_PROMPT = (
    "你是一位專業、友善的 AI 語音助理，支援加入餐點與語音問答兩種模式。\n"
    "若顧客直接說出想點的餐點與數量，輸出 cart_actions；否則用自然口語回答。\n"
    "禁止創造菜單不存在的餐點、價格或 ID。\n"
    "只輸出合法 JSON：\n"
    '{"ai_response":"回答","mentioned_ids":[],"cart_actions":[]}'
)


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
    menu_items = await asyncio.to_thread(menu_repository.get_menu)
    full_menu_context = await asyncio.to_thread(database.build_full_menu_context)

    if detected_lang == "en":
        system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT_EN") or _DEFAULT_SYSTEM_PROMPT
    else:
        system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT") or _DEFAULT_SYSTEM_PROMPT

    # RAG context 注入
    if config.get("RAG_ENABLED", False):
        from services.rag_provider import get_rag
        rag_context = await get_rag().query(user_text)
    else:
        rag_context = ""

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

    user_prompt = (
        f"【顧客語音輸入】\n{user_text}\n\n"
        + (f"{emotion_context}\n\n" if emotion_context else "")
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
