"""語音助理服務：STT → Ollama → TTS。"""
import asyncio

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from services.recommendation_service import coerce_cart_actions

_DEFAULT_SYSTEM_PROMPT = (
    "你是麥當勞自助點餐機的語音助理。"
    "根據顧客語音輸入協助點餐或回答菜單問題。"
    "若顧客要點餐，輸出 cart_actions；若是問答，cart_actions 輸出空陣列。"
    "只能使用菜單白名單中的餐點 ID，不得創造不存在的餐點。"
    '只輸出合法 JSON：{"ai_response":"回覆","cart_actions":[{"action":"add","id":"MCDxxx","quantity":1}]}'
)


async def handle_voice(
    session_id: str,
    audio_path: str,
    ollama_semaphore,
    multi_lang: bool = True,
) -> dict:
    # 1. Whisper STT
    stt = await ai_services.async_safe_transcribe_with_language(audio_path)
    user_text = (stt.get("text") or "").strip()
    detected_lang = stt.get("language", "zh") if multi_lang else "zh"

    if not user_text:
        return {
            "status": "error",
            "message": "無法辨識語音內容",
            "user_text": "",
            "ai_response": "",
            "audio_base64": "",
            "cart_actions": [],
            "detected_lang": detected_lang,
        }

    menu_items = await asyncio.to_thread(menu_repository.get_menu)
    full_menu_context = await asyncio.to_thread(database.build_full_menu_context)
    if detected_lang == "en":
        system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT_EN") or _DEFAULT_SYSTEM_PROMPT
    else:
        system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT") or _DEFAULT_SYSTEM_PROMPT

    # TODO: inject RAG context here
    # rag_context = rag_provider.query(user_text)
    user_prompt = f"【顧客語音輸入】\n{user_text}\n\n{full_menu_context}"

    # 2. Ollama
    model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
    async with ollama_semaphore:
        result = await asyncio.to_thread(
            ai_services.ask_ollama, system_prompt, user_prompt, "", model
        )

    if not isinstance(result, dict) or "error" in result:
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
            user_text,
            menu_items,
        )
        if not ai_response:
            if detected_lang == "en":
                ai_response = "Added to your cart." if cart_actions else "I can help with menu questions or add items to your cart."
            else:
                ai_response = "已為您加入購物車。" if cart_actions else "我可以協助您了解菜單或加入餐點。"

    session_repository.record_session_state(
        session_id=session_id,
        emotion="",
        user_speech=user_text,
        ai_response=ai_response,
        language=detected_lang,
    )

    # 3. TTS
    audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)

    return {
        "status": "success",
        "user_text": user_text,
        "ai_response": ai_response,
        "audio_base64": audio_base64,
        "cart_actions": cart_actions,
        "detected_lang": detected_lang,
    }
