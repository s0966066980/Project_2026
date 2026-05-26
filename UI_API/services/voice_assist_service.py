"""語音協助服務：語音點餐 + 語音問答，使用 qwen3.5:9b。"""
import asyncio

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from services import recommendation_service
from services import query_router_service


def _cart_action_names(cart_actions: list[dict], menu_items: list[dict]) -> list[str]:
    names = []
    for action in cart_actions:
        item = next((m for m in menu_items if m.get("id") == action.get("id")), None)
        if item:
            names.append(f"{item.get('name')} x{action.get('quantity', 1)}")
    return names


async def handle_voice_assist(
    session_id: str,
    audio_path: str,
    multi_lang: bool,
    ollama_semaphore,
    emotion_structured: dict | None = None,
) -> dict:
    """
    主入口：STT → 意圖路由 → qwen3.5:9b 問答 or 直接點餐。
    emotion_structured: 由語音協助觸發時可選傳入 Emotion-LLaMA 分析結果。
    """
    loop = asyncio.get_running_loop()
    stt_result = await ai_services.async_safe_transcribe_with_language(audio_path)
    user_text = (stt_result.get("text") or "").strip()
    detected_lang = stt_result.get("language", "zh") if multi_lang else "zh"

    if not user_text:
        return {"status": "error", "message": "無法辨識語音內容"}

    menu_items = await asyncio.to_thread(menu_repository.get_menu)
    route = query_router_service.route_query(user_text, menu_items)
    intent = route.get("intent", "")
    # 與 AI 推播使用同一模型（MODEL_NAME），VOICE_ASSIST_MODEL 作為備選
    model = config.get("MODEL_NAME", "qwen3.5:4b")
    fallback_model = config.get("VOICE_ASSIST_MODEL", model)

    # ---- 直接點餐 ----
    if intent == "direct_order":
        cart_actions = recommendation_service.coerce_cart_actions([], user_text, menu_items)
        if cart_actions:
            names = _cart_action_names(cart_actions, menu_items)
            ai_response = (
                ("Added to cart: " + ", ".join(names)) if detected_lang == "en"
                else "已幫您加入購物車：" + "、".join(names)
            )
            session_repository.record_session_state(
                session_id=session_id, emotion="",
                user_speech=user_text, ai_response=ai_response,
                language=detected_lang,
            )
            audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
            return {
                "status": "success",
                "mode": "direct_order",
                "user_text": user_text,
                "ai_response": ai_response,
                "audio_base64": audio_base64,
                "cart_actions": cart_actions,
                "mentioned_ids": [],
                "detected_lang": detected_lang,
                "trigger_recommend": False,
            }

    # ---- 菜單直接查詢（不需 LLM，僅限明確品項查詢，推薦類一律走 LLM）----
    if intent == "menu_question":
        menu_answer = recommendation_service.answer_menu_question_from_text(user_text, menu_items)
        # 若靜態回覆有確定結果且非推薦意圖，直接回覆以節省 Ollama 資源
        recommend_keywords = ["推薦", "recommend", "建議", "幫我選", "幫我挑", "什麼好", "好吃"]
        is_recommend_query = any(kw in user_text for kw in recommend_keywords)
        if menu_answer and not is_recommend_query:
            ai_response = menu_answer.get("ai_response", "")
            mentioned_ids = menu_answer.get("mentioned_ids", [])
            session_repository.record_session_state(
                session_id=session_id, emotion="",
                user_speech=user_text, ai_response=ai_response,
                language=detected_lang,
            )
            audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
            return {
                "status": "success",
                "mode": "menu_question",
                "user_text": user_text,
                "ai_response": ai_response,
                "audio_base64": audio_base64,
                "cart_actions": [],
                "mentioned_ids": mentioned_ids,
                "detected_lang": detected_lang,
                "trigger_recommend": True,
            }
        # 推薦意圖或靜態無結果 → 落入 Ollama LLM

    # ---- 通用 LLM 問答 ----
    full_menu_context = await asyncio.to_thread(database.build_full_menu_context)
    global_context = await asyncio.to_thread(database.get_global_rag_context)
    rag_context = str(global_context or "").strip()

    # 加入 Emotion-LLaMA 證據（如有）
    emotion_hint = ""
    if emotion_structured and not emotion_structured.get("no_person"):
        label = emotion_structured.get("emotion_label") or emotion_structured.get("emotion_display") or ""
        evidence = emotion_structured.get("emotion_evidence") or ""
        if label:
            emotion_hint = f"【情緒分析】顧客情緒：{label}。{evidence}\n\n"

    if detected_lang == "en":
        system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT_EN")
        lang_contract = "Language contract: the customer spoke English. Reply in English only."
    else:
        system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT")
        lang_contract = "語言契約：顧客使用中文。請只用繁體中文回答。"

    user_prompt = (
        f"{emotion_hint}"
        f"{lang_contract}\n\n"
        f"【顧客語音輸入】\n{user_text}\n\n"
        f"{full_menu_context}\n\n"
        f"【RAG 補充內容】\n{rag_context or '（無補充）'}\n\n"
        "若顧客直接點餐，輸出 cart_actions；若是問答，cart_actions 輸出空陣列。\n"
        "mentioned_ids 只能使用完整菜單白名單中的 ID。"
    )

    async with ollama_semaphore:
        result = await loop.run_in_executor(
            None, ai_services.ask_ollama, system_prompt, user_prompt, "", model
        )
        # 若指定模型不存在，以 fallback_model 重試一次
        if isinstance(result, dict) and "error" in result and model != fallback_model:
            result = await loop.run_in_executor(
                None, ai_services.ask_ollama, system_prompt, user_prompt, "", fallback_model
            )

    if isinstance(result, list):
        result = next((r for r in result if isinstance(r, dict)), {})
    elif not isinstance(result, dict):
        result = {}

    if "error" in result:
        fallback = (
            "Sorry, please try again or tap a menu item directly."
            if detected_lang == "en"
            else "暫時無法回答，請直接點選菜單或稍後再試。"
        )
        return {
            "status": "error",
            "message": result.get("error", "llm_error"),
            "ai_response": fallback,
            "audio_base64": await ai_services.generate_tts_audio_base64(fallback, lang=detected_lang),
            "cart_actions": [],
            "mentioned_ids": [],
            "detected_lang": detected_lang,
        }

    ai_response = str(result.get("ai_response") or "").strip()
    menu_ids = [item.get("id") for item in menu_items if item.get("id")]
    raw_mentioned = result.get("mentioned_ids") or []
    if isinstance(raw_mentioned, str):
        raw_mentioned = [raw_mentioned]
    mentioned_ids = [
        recommendation_service.clean_menu_id(rid, menu_ids)
        for rid in raw_mentioned
        if recommendation_service.clean_menu_id(rid, menu_ids)
    ]
    raw_cart = result.get("cart_actions") or []
    cart_actions = recommendation_service.coerce_cart_actions(
        raw_cart if isinstance(raw_cart, list) else [],
        user_text, menu_items
    )
    if not ai_response:
        ai_response = (
            "I can help with menu questions or add items to your cart."
            if detected_lang == "en"
            else "我可以協助您了解菜單或加入餐點。"
        )
    ai_response = recommendation_service.fix_ask_reply_for_intent(
        user_text, detected_lang, ai_response, cart_actions, mentioned_ids
    )
    session_repository.record_session_state(
        session_id=session_id, emotion="",
        user_speech=user_text, ai_response=ai_response,
        language=detected_lang,
    )
    audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
    return {
        "status": "success",
        "mode": "voice_assist",
        "user_text": user_text,
        "ai_response": ai_response,
        "audio_base64": audio_base64,
        "cart_actions": cart_actions,
        "mentioned_ids": mentioned_ids,
        "detected_lang": detected_lang,
        "trigger_recommend": bool(mentioned_ids) or intent == "ask_recommendation",
    }
