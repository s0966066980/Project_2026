import asyncio
import re
import time

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from services import rag_review_service
from services import recommendation_service


def _cart_action_names(cart_actions: list[dict], menu_items: list[dict]) -> list[str]:
    names = []
    for action in cart_actions:
        item = next((row for row in menu_items if row.get("id") == action.get("id")), None)
        if item:
            names.append(f"{item.get('name')} x{action.get('quantity', 1)}")
    return names


def _looks_like_direct_order(user_text: str) -> bool:
    normalized = recommendation_service.normalize_order_text(user_text)
    if not normalized:
        return False
    direct_terms = [
        "我要", "幫我加", "幫我點", "加一", "加兩", "加2", "點一", "點兩",
        "點2", "來一", "來兩", "來2", "一份", "兩份", "2份", "一個", "兩個",
        "2個", "一杯", "兩杯", "2杯", "一組", "兩組", "2組",
    ]
    if any(term in normalized for term in direct_terms):
        return True
    return bool(re.search(r"\d+\s*(份|個|杯|組)", normalized))


def build_voice_order_rag_text(
    session_id: str,
    user_text: str,
    detected_lang: str,
    mode: str,
    ai_response: str,
    cart_actions: list[dict],
    menu_items: list[dict],
) -> str:
    matched = _cart_action_names(cart_actions, menu_items)
    return (
        "語音點餐對話紀錄\n"
        f"Session: {session_id}\n"
        f"語言: {detected_lang}\n"
        f"模式: {mode}\n"
        f"顧客語音文字: {user_text}\n"
        f"系統回覆: {ai_response}\n"
        f"成功加入購物車: {'、'.join(matched) if matched else '無'}\n"
        f"cart_actions: {cart_actions}"
    )


async def _save_voice_order_rag_doc(
    session_id: str,
    user_text: str,
    detected_lang: str,
    mode: str,
    ai_response: str,
    cart_actions: list[dict],
    menu_items: list[dict],
    ollama_semaphore,
    schedule_rag_rebuild=None,
):
    try:
        source_id = f"voice_order_{session_id}_{int(time.time() * 1000)}"
        source_text = build_voice_order_rag_text(
            session_id, user_text, detected_lang, mode, ai_response, cart_actions, menu_items
        )
        review_result = await rag_review_service.review_rag_text(
            source_text, "voice_order", source_id, ollama_semaphore
        )
        await asyncio.to_thread(
            database.upsert_reviewed_rag_doc,
            "voice_order", source_id, source_text, review_result
        )
        if schedule_rag_rebuild:
            schedule_rag_rebuild("voice order RAG doc")
    except Exception as e:
        print(f"⚠️ 語音點餐 RAG 審查保存失敗: {e}")


async def handle_voice_ask(
    session_id: str,
    audio_path: str,
    multi_lang: bool,
    use_ollama: bool,
    ollama_semaphore,
    schedule_rag_rebuild=None,
) -> dict:
    loop = asyncio.get_running_loop()
    stt_result = await ai_services.async_safe_transcribe_with_language(audio_path)
    user_text = stt_result["text"]
    detected_lang = stt_result["language"] if multi_lang else "zh"

    if not user_text.strip():
        return {"status": "error", "message": "無法辨識語音內容"}

    menu_items = await asyncio.to_thread(menu_repository.get_menu)
    
    if _looks_like_direct_order(user_text):
        cart_actions = recommendation_service.coerce_cart_actions([], user_text, menu_items)
        if cart_actions:
            names = _cart_action_names(cart_actions, menu_items)
            ai_response = "已幫您加入購物車：" + "、".join(names)
            if detected_lang == "en":
                ai_response = "Added to cart: " + ", ".join(names)
            session_repository.record_session_state(
                session_id=session_id, emotion="",
                user_speech=user_text, ai_response=ai_response,
                language=detected_lang
            )
            asyncio.create_task(_save_voice_order_rag_doc(
                session_id, user_text, detected_lang, "direct_order", ai_response,
                cart_actions, menu_items, ollama_semaphore, schedule_rag_rebuild
            ))
            return {
                "status": "success",
                "mode": "direct_order",
                "user_text": user_text,
                "ai_response": ai_response,
                "audio_base64": "",
                "mentioned_ids": [],
                "cart_actions": cart_actions,
                "detected_lang": detected_lang,
                "raw_detected_lang": stt_result.get("raw_language", ""),
                "trigger_recommend": False
            }

    if not use_ollama:
        cart_actions = recommendation_service.coerce_cart_actions([], user_text, menu_items)
        names = _cart_action_names(cart_actions, menu_items)
        ai_response = ("已加入購物車：" + "、".join(names)) if names else "沒有在菜單中找到可加入購物車的餐點。"
        if detected_lang == "en":
            ai_response = ("Added to cart: " + ", ".join(names)) if names else "I could not find that item on the menu."
        session_repository.record_session_state(
            session_id=session_id, emotion="",
            user_speech=user_text, ai_response=ai_response,
            language=detected_lang
        )
        asyncio.create_task(_save_voice_order_rag_doc(
            session_id, user_text, detected_lang, "order_only", ai_response,
            cart_actions, menu_items, ollama_semaphore, schedule_rag_rebuild
        ))
        return {
            "status": "success",
            "mode": "order_only",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": "",
            "mentioned_ids": [],
            "cart_actions": cart_actions,
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "trigger_recommend": False
        }

    full_menu_context = await asyncio.to_thread(database.build_full_menu_context)
    rag_details = await asyncio.to_thread(database.retrieve_rag_details, user_text)
    rag_context = rag_details.get("context", "")
    qa_provider = str(config.get("QA_AI_PROVIDER", "ollama") or "ollama").lower()
    source_rule = (
        "Gemini 回覆不需要在 ai_response 說明來源、引用 file_name、page 或 chunk_id。\n"
        if qa_provider == "gemini"
        else "如果使用 RAG 補充內容回答，請在 ai_response 末尾附上來源 file_name、page、chunk_id。\n"
    )

    if detected_lang == "en":
        ask_system = config.get("ASK_SYSTEM_PROMPT_EN")
        language_contract = "Language contract: the customer spoke English. Reply in English only."
    else:
        ask_system = config.get("ASK_SYSTEM_PROMPT")
        language_contract = "語言契約：顧客使用中文發問。請只用繁體中文回答。"

    user_prompt = (
        f"{language_contract}\n\n"
        f"【顧客詢問】：{user_text}\n\n"
        f"{full_menu_context}\n\n"
        f"【RAG 補充內容】\n{rag_context}\n\n"
        "重要限制：請優先遵守【RAG 補充內容】與【RAG 全域規則】中的指示。若無衝突，回答只能引用完整菜單白名單中的餐點、價格與資訊。\n"
        f"{source_rule}"
        "如果顧客是在直接點餐，例如說「我要兩份炸雞」、「加一杯咖啡」，請在 JSON 加上 cart_actions。\n"
        "如果顧客表示很急、趕時間、要很快做好的餐點，請根據完整菜單白名單中的製作時間篩選較快完成的餐點。\n"
        "cart_actions 格式固定為 [{\"action\":\"add\",\"id\":\"菜單ID\",\"quantity\":數量}]；id 必須來自完整菜單白名單，quantity 介於 1 到 10。\n"
        "如果只是詢問或推薦，cart_actions 請輸出空陣列。"
    )
    
    # 1. 檢查檢索品質
    rag_settings = rag_details.get("settings", {})
    import rag_service
    is_sufficient = rag_service.is_context_sufficient(rag_details)
    
    if not is_sufficient:
        # RAG 文件不足，拒答或依賴菜單白名單 fallback
        menu_question_answer = recommendation_service.answer_menu_question_from_text(user_text, menu_items)
        if menu_question_answer and not _looks_like_direct_order(user_text):
            ai_response = menu_question_answer.get("ai_response", "")
            mentioned_ids = menu_question_answer.get("mentioned_ids", [])
            cart_actions = []
        else:
            ai_response = "目前資料庫沒有足夠資訊回答這個問題，請在後台 RAG 文本新增對應資料。"
            mentioned_ids = []
            cart_actions = recommendation_service.coerce_cart_actions([], user_text, menu_items)
        
        ask_result = {
            "ai_response": ai_response,
            "mentioned_ids": mentioned_ids,
            "cart_actions": cart_actions
        }
    else:
        # 有足夠 RAG 資訊，呼叫 LLM
        async with ollama_semaphore:
            # 決定溫度 (llama3.2 QA 用 0.1)
            model_name = config.get("ASK_MODEL_NAME", "llama3.2")
            temp = 0.1 if ("llama" in model_name.lower() or qa_provider == "ollama") else None
            
            ask_result = await loop.run_in_executor(
                None,
                ai_services.ask_llm,
                ask_system,
                user_prompt,
                "ASK",
                model_name,
                qa_provider,
                temp
            )
            
        # 驗證生成結果
        if rag_settings.get("answer_verification", True) and "error" not in ask_result:
            verification_context = full_menu_context + "\n\n" + rag_context
            verification = await loop.run_in_executor(
                None,
                rag_service.verify_answer_grounding,
                user_text,
                ask_result.get("ai_response", ""),
                verification_context
            )
            if not verification.get("grounded", True):
                ask_result["ai_response"] = verification.get("safe_answer", "目前資料庫沒有足夠資訊回答這個問題。")
                ask_result["mentioned_ids"] = []
                if not _looks_like_direct_order(user_text):
                    ask_result["cart_actions"] = []


    fallback_response = "Sorry, I am still thinking. Please try again." if detected_lang == "en" else "抱歉，系統思考中。"
    ai_response = (ask_result.get("ai_response", fallback_response)
                   if "error" not in ask_result else fallback_response)
    mentioned_ids = ask_result.get("mentioned_ids", [])
    if isinstance(mentioned_ids, str):
        mentioned_ids = [mentioned_ids]
    elif not isinstance(mentioned_ids, list):
        mentioned_ids = []
    menu_ids = [item.get("id") for item in menu_items if item.get("id")]
    mentioned_ids = [recommendation_service.clean_menu_id(item_id, menu_ids) for item_id in mentioned_ids]
    mentioned_ids = [item_id for item_id in mentioned_ids if item_id]
    cart_actions = recommendation_service.coerce_cart_actions(
        ask_result.get("cart_actions", []), user_text, menu_items
    )
    menu_question_answer = recommendation_service.answer_menu_question_from_text(user_text, menu_items)
    if menu_question_answer and not _looks_like_direct_order(user_text):
        cart_actions = []
        ai_response = menu_question_answer.get("ai_response", ai_response) or ai_response
        mentioned_ids = menu_question_answer.get("mentioned_ids", mentioned_ids) or mentioned_ids
    elif menu_question_answer and not cart_actions:
        ai_response = menu_question_answer.get("ai_response", ai_response) or ai_response
        mentioned_ids = menu_question_answer.get("mentioned_ids", mentioned_ids) or mentioned_ids
    ai_response = recommendation_service.fix_ask_reply_for_intent(
        user_text, detected_lang, ai_response, cart_actions, mentioned_ids
    )
    if cart_actions and detected_lang != "en":
        names = _cart_action_names(cart_actions, menu_items)
        bad_reply = any(phrase in (ai_response or "") for phrase in ["抱歉", "沒有這個品項", "菜單沒有", "找不到", "目前菜單沒有"])
        not_confirming_cart = "加入" not in (ai_response or "") and "購物車" not in (ai_response or "")
        if names and (not ai_response or bad_reply or not_confirming_cart):
            ai_response = "已幫您加入購物車：" + "、".join(names)

    session_repository.record_session_state(
        session_id=session_id, emotion="",
        user_speech=user_text, ai_response=ai_response,
        language=detected_lang
    )
    save_voice_order_to_rag = bool(config.get("SAVE_VOICE_ORDER_TO_RAG", False))
    demo_save_voice_order_to_rag = bool(config.get("DEMO_SAVE_VOICE_ORDER_TO_RAG", False))
    if save_voice_order_to_rag and (not config.is_demo_public_mode() or demo_save_voice_order_to_rag):
        asyncio.create_task(_save_voice_order_rag_doc(
            session_id, user_text, detected_lang, qa_provider, ai_response,
            cart_actions, menu_items, ollama_semaphore, schedule_rag_rebuild
        ))

    audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
    dialogue = {
        "zh": {
            "user_text": user_text if detected_lang == "zh" else "",
            "ai_response": ai_response if detected_lang == "zh" else ""
        },
        "en": {
            "user_text": user_text if detected_lang == "en" else "",
            "ai_response": ai_response if detected_lang == "en" else ""
        }
    }

    return {
        "status": "success",
        "user_text": user_text,
        "ai_response": ai_response,
        "audio_base64": audio_base64,
        "mentioned_ids": mentioned_ids,
        "cart_actions": cart_actions,
        "detected_lang": detected_lang,
        "raw_detected_lang": stt_result.get("raw_language", ""),
        "dialogue": dialogue,
        "citations": [] if qa_provider == "gemini" else rag_details.get("citations", []),
        "retrieval_evaluation": rag_details.get("evaluation", {}),
        "trigger_recommend": not bool(cart_actions)
    }
