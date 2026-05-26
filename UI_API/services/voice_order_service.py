import asyncio
import time

import ai_services
import config
import database
import rag_service
from repositories import menu_repository, session_repository
from services import rag_review_service
from services import query_router_service
from services import recommendation_service


VOICE_PATHS = {
    "direct_order": "menu.json -> cart_actions, no RAG unless SAVE_VOICE_ORDER_TO_RAG=true",
    "menu_question": "menu.json + recommendation_service, RAG only supplements global rules",
    "ask_recommendation": "menu.json + recommendation_service, RAG only supplements global rules",
    "rag_question": "strict RAG with retrieve_with_retry and claim verification",
    "service_question": "strict RAG or customer-service assist depending on wording",
}


def _cart_action_names(cart_actions: list[dict], menu_items: list[dict]) -> list[str]:
    names = []
    for action in cart_actions:
        item = next((row for row in menu_items if row.get("id") == action.get("id")), None)
        if item:
            names.append(f"{item.get('name')} x{action.get('quantity', 1)}")
    return names


def _looks_like_service_request(user_text: str) -> bool:
    normalized = recommendation_service.normalize_order_text(user_text)
    if not normalized:
        return False
    # 限縮為「明確請求客服 / 反映問題」的短語，避免「幫我加一份薯條」這類點餐請求誤判
    terms = [
        "找客服", "叫客服", "請客服", "需要客服",
        "找店員", "叫店員", "請店員", "需要店員", "店員協助",
        "找真人", "叫真人", "需要真人", "真人協助",
        "幫我處理", "請幫忙", "需要幫忙", "請協助",
        "不會操作", "不會用", "不會點",
        "看不懂", "怎麼操作", "怎麼用", "怎麼點",
        "不能刷", "付款失敗", "刷卡失敗",
        "客訴", "投訴", "找經理", "不爽", "太慢", "等很久",
        "call staff", "need staff", "cashier", "manager", "complaint",
    ]
    return any(term in normalized for term in terms)


def _service_assist_reply(user_text: str, detected_lang: str) -> str:
    normalized = recommendation_service.normalize_order_text(user_text)
    if detected_lang == "en":
        if any(term in normalized for term in ["pay", "card", "line pay", "payment"]):
            return "I can help with payment. Please choose the payment method on the screen. If it still fails, staff will assist you."
        return "I can help. Please choose a category first, then tap the plus button next to the item to add it to your cart."
    if any(term in normalized for term in ["不能刷", "付款", "刷卡", "line pay", "悠遊卡", "支付"]):
        return "我可以協助您付款。請先在付款頁選擇點點卡、信用卡或掃碼支付；如果仍然失敗，店員會協助您。"
    if any(term in normalized for term in ["客訴", "投訴", "經理", "不爽", "太慢", "等很久"]):
        return "不好意思讓您久等了，我會通知店員協助您處理。"
    return "我可以協助您操作。請先選擇餐點分類，再點餐點旁的加號加入購物車；需要付款時再按結帳。"


def _dialogue(user_text: str, ai_response: str, detected_lang: str) -> dict:
    return {
        "zh": {
            "user_text": user_text if detected_lang == "zh" else "",
            "ai_response": ai_response if detected_lang == "zh" else ""
        },
        "en": {
            "user_text": user_text if detected_lang == "en" else "",
            "ai_response": ai_response if detected_lang == "en" else ""
        }
    }


def _runtime_setting_reply(user_text: str, detected_lang: str) -> str:
    if config.is_demo_public_mode() or not config.get("ALLOW_POS_RUNTIME_SETTING_QUERY", False):
        if detected_lang == "en":
            return "The system has AI ordering, menu recommendations, and customer support assistance enabled."
        return "目前系統已啟用 AI 點餐、菜單推薦與客服協助功能。"

    status = rag_service.get_status()
    customer_mode = config.get("CUSTOMER_SERVICE_MODE", "ollama")
    ask_model = config.get("ASK_MODEL_NAME", "llama3.2")
    model_name = config.get("MODEL_NAME", "llama3.2")
    recommend_interval = config.get("RECOMMEND_INTERVAL_SEC", 30)
    rag_ready = "已就緒" if status.get("rag_ready") else "未就緒"
    if detected_lang == "en":
        return (
            f"Current service mode is {customer_mode}. "
            f"QA model is {ask_model}; local default model is {model_name}. "
            f"RAG is {rag_ready}, with {status.get('chunk_count', 0)} chunks. "
            f"Recommendation interval is {recommend_interval} seconds."
        )
    return (
        f"目前客服模式是 {customer_mode}。"
        f"語音問答模型是 {ask_model}，本地預設模型是 {model_name}。"
        f"RAG 狀態：{rag_ready}，目前有 {status.get('chunk_count', 0)} 個 chunk。"
        f"主動推薦間隔為 {recommend_interval} 秒。"
    )


async def _answer_recommendation_with_menu_llm(
    user_text: str,
    detected_lang: str,
    menu_items: list[dict],
    ollama_semaphore,
) -> dict:
    loop = asyncio.get_running_loop()
    full_menu_context = await asyncio.to_thread(database.build_full_menu_context)
    global_context = await asyncio.to_thread(database.get_global_rag_context)
    rag_context = str(global_context or "").strip()
    retrieval_evaluation = {
        "sufficient": True,
        "reason": "menu_recommendation_global_rules_only",
    }

    if detected_lang == "en":
        ask_system = config.get("ASK_SYSTEM_PROMPT_EN")
        language_contract = "Language contract: the customer asked in English. Reply in English only."
    else:
        ask_system = config.get("ASK_SYSTEM_PROMPT")
        language_contract = "語言契約：顧客使用中文詢問推薦。請只用繁體中文回答。"

    user_prompt = (
        f"{language_contract}\n\n"
        f"【顧客詢問推薦】\n{user_text}\n\n"
        f"{full_menu_context}\n\n"
        f"【RAG 補充內容】\n{rag_context or '本次沒有額外 RAG 補充，仍可根據完整菜單白名單推薦。'}\n\n"
        "任務：直接推薦 1 到 3 個真實菜單品項。優先使用 RAG 全域規則與補充內容；"
        "若 RAG 沒有相關補充，仍必須使用完整菜單白名單與基本 LLM 判斷回答，不能輸出通用預設回覆。\n"
        "mentioned_ids 必須是完整菜單白名單中的 ID；如果只是推薦，cart_actions 請輸出空陣列。"
    )

    async with ollama_semaphore:
        ask_result = await loop.run_in_executor(
            None,
            ai_services.ask_llm,
            ask_system,
            user_prompt,
            "ASK_RECOMMEND",
            config.get("ASK_MODEL_NAME", "llama3.2"),
            config.get("QA_AI_PROVIDER", "ollama"),
            0.2,
        )

    menu_ids = [item.get("id") for item in menu_items if item.get("id")]
    if "error" not in ask_result and str(ask_result.get("ai_response") or "").strip():
        raw_ids = ask_result.get("mentioned_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        mentioned_ids = [
            recommendation_service.clean_menu_id(item_id, menu_ids)
            for item_id in (raw_ids if isinstance(raw_ids, list) else [])
        ]
        mentioned_ids = [item_id for item_id in mentioned_ids if item_id]
        reply = recommendation_service.fix_ask_reply_for_intent(
            user_text,
            detected_lang,
            str(ask_result.get("ai_response") or "").strip(),
            [],
            mentioned_ids,
        )
        return {
            "ok": True,
            "ai_response": reply,
            "mentioned_ids": mentioned_ids,
            "rag_debug": {
                "source": "menu_recommendation_llm",
                "quality_gate": None,
                "retrieval_evaluation": retrieval_evaluation,
                "citations": [],
                "voice_path": VOICE_PATHS["ask_recommendation"],
            },
            "citations": [],
            "retrieval_evaluation": retrieval_evaluation,
        }

    menu_answer = recommendation_service.answer_menu_question_from_text(user_text, menu_items)
    if menu_answer:
        return {
            "ok": True,
            "ai_response": menu_answer.get("ai_response", ""),
            "mentioned_ids": menu_answer.get("mentioned_ids", []),
            "rag_debug": {
                "source": "menu_whitelist_fallback",
                "llm_error": ask_result.get("error", ""),
                "quality_gate": None,
                "retrieval_evaluation": retrieval_evaluation,
                "citations": [],
                "voice_path": VOICE_PATHS["ask_recommendation"],
            },
            "citations": [],
            "retrieval_evaluation": retrieval_evaluation,
        }
    return {"ok": False, "error": ask_result.get("error", "recommendation_unavailable"), "rag_debug": {"source": "failed"}}


def _should_save_voice_order_to_rag() -> bool:
    save_voice_order_to_rag = bool(config.get("SAVE_VOICE_ORDER_TO_RAG", False))
    demo_save_voice_order_to_rag = bool(config.get("DEMO_SAVE_VOICE_ORDER_TO_RAG", False))
    return save_voice_order_to_rag and (not config.is_demo_public_mode() or demo_save_voice_order_to_rag)


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
    route = query_router_service.route_query(user_text, menu_items)

    if use_ollama and route.get("intent") != "direct_order" and _looks_like_service_request(user_text):
        ai_response = _service_assist_reply(user_text, detected_lang)
        session_repository.record_session_state(
            session_id=session_id, emotion="",
            user_speech=user_text, ai_response=ai_response,
            language=detected_lang
        )
        audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
        return {
            "status": "success",
            "mode": "service_assist",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": audio_base64,
            "mentioned_ids": [],
            "cart_actions": [],
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "dialogue": _dialogue(user_text, ai_response, detected_lang),
            "citations": [],
            "retrieval_evaluation": {"sufficient": True, "reason": "service_assist_rule"},
            "rag_debug": {"route": route},
            "trigger_recommend": False
        }
    
    if use_ollama and route.get("intent") == "direct_order":
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
            if _should_save_voice_order_to_rag() and cart_actions:
                asyncio.create_task(_save_voice_order_rag_doc(
                    session_id, user_text, detected_lang, "direct_order", ai_response,
                    cart_actions, menu_items, ollama_semaphore, schedule_rag_rebuild
                ))
            audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
            return {
                "status": "success",
                "mode": "direct_order",
                "user_text": user_text,
                "ai_response": ai_response,
                "audio_base64": audio_base64,
                "mentioned_ids": [],
                "cart_actions": cart_actions,
                "detected_lang": detected_lang,
                "raw_detected_lang": stt_result.get("raw_language", ""),
                "dialogue": _dialogue(user_text, ai_response, detected_lang),
                "rag_debug": {"route": route},
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
        if _should_save_voice_order_to_rag() and cart_actions:
            asyncio.create_task(_save_voice_order_rag_doc(
                session_id, user_text, detected_lang, "order_only", ai_response,
                cart_actions, menu_items, ollama_semaphore, schedule_rag_rebuild
            ))
        audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
        return {
            "status": "success",
            "mode": "order_only",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": audio_base64,
            "mentioned_ids": [],
            "cart_actions": cart_actions,
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "dialogue": _dialogue(user_text, ai_response, detected_lang),
            "rag_debug": {"route": route},
            "trigger_recommend": False
        }

    full_menu_context = await asyncio.to_thread(database.build_full_menu_context)
    menu_question_answer = (
        recommendation_service.answer_menu_question_from_text(user_text, menu_items)
        if route.get("intent") == "menu_question"
        else {}
    )
    if route.get("intent") == "menu_question" and menu_question_answer:
        ai_response = menu_question_answer.get("ai_response", "")
        mentioned_ids = menu_question_answer.get("mentioned_ids", [])
        session_repository.record_session_state(
            session_id=session_id, emotion="",
            user_speech=user_text, ai_response=ai_response,
            language=detected_lang
        )
        audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
        return {
            "status": "success",
            "mode": "menu_question",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": audio_base64,
            "mentioned_ids": mentioned_ids,
            "cart_actions": [],
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "dialogue": _dialogue(user_text, ai_response, detected_lang),
            "citations": [],
            "retrieval_evaluation": {"sufficient": True, "reason": "menu_whitelist_answer"},
            "rag_debug": {
                "route": route,
                "quality_gate": None,
                "retrieval_evaluation": {"sufficient": True, "reason": "menu_whitelist_answer"},
                "citations": [],
                "verification": None,
            },
            "trigger_recommend": True
        }

    if use_ollama and route.get("intent") == "ask_recommendation":
        rag_answer = await _answer_recommendation_with_menu_llm(
            user_text,
            detected_lang,
            menu_items,
            ollama_semaphore,
        )
        rec = {}
        rec_ids = rag_answer.get("mentioned_ids", []) if rag_answer.get("ok") else []
        rec_reason = ""
        ai_response = rag_answer.get("ai_response", "") if rag_answer.get("ok") else ""
        if not ai_response:
            rec = await recommendation_service.generate_recommendation(
                session_id=session_id,
                emotion_cache={},
                ollama_semaphore=ollama_semaphore,
            )
            if rec.get("status") == "success":
                rec_ids = rec.get("recommendation_ids") or []
                rec_reason = rec.get("reason") or ""
            name_by_id = {item.get("id"): item.get("name") for item in menu_items if item.get("id")}
            rec_names = [name_by_id.get(rid) for rid in rec_ids if name_by_id.get(rid)]
            if rec_names:
                if detected_lang == "en":
                    ai_response = f"How about {', '.join(rec_names[:3])}? {rec_reason}".strip()
                else:
                    ai_response = (rec_reason or "為您推薦：") + "、".join(rec_names[:3])
            else:
                ai_response = (
                    "I can recommend from the current menu after the local model is available."
                    if detected_lang == "en"
                    else "目前本地模型暫時無法產生推薦，請稍後再試；也可以直接說想吃主餐、飲料或點心。"
                )
        session_repository.record_session_state(
            session_id=session_id, emotion="",
            user_speech=user_text, ai_response=ai_response,
            language=detected_lang
        )
        audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
        return {
            "status": "success",
            "mode": "ask_recommendation",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": audio_base64,
            "mentioned_ids": rec_ids,
            "cart_actions": [],
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "dialogue": _dialogue(user_text, ai_response, detected_lang),
            "citations": rag_answer.get("citations", []),
            "retrieval_evaluation": rag_answer.get("retrieval_evaluation", {"sufficient": True, "reason": "ask_recommendation"}),
            "rag_debug": {"route": route, "recommendation": rec, **(rag_answer.get("rag_debug") or {})},
            "recommendation_ids": rec_ids,
            "recommendation_reason": rec_reason,
            "trigger_recommend": True,
        }

    if route.get("intent") == "menu_question":
        categories = []
        for item in menu_items:
            category = str(item.get("category") or "").strip()
            if category and category not in categories:
                categories.append(category)
        if detected_lang == "en":
            ai_response = "You can ask about current menu categories such as " + ", ".join(categories[:6]) + "."
        else:
            ai_response = "目前可依菜單分類協助推薦，例如：" + "、".join(categories[:6]) + "。也可以直接說想吃雞肉、牛肉、點心或飲料。"
        session_repository.record_session_state(
            session_id=session_id, emotion="",
            user_speech=user_text, ai_response=ai_response,
            language=detected_lang
        )
        audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
        return {
            "status": "success",
            "mode": "menu_question",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": audio_base64,
            "mentioned_ids": [],
            "cart_actions": [],
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "dialogue": _dialogue(user_text, ai_response, detected_lang),
            "citations": [],
            "retrieval_evaluation": {"sufficient": True, "reason": "menu_question_menu_whitelist_fallback"},
            "rag_debug": {"route": route, "voice_path": VOICE_PATHS["menu_question"]},
            "trigger_recommend": True,
        }

    if route.get("intent") == "runtime_setting":
        ai_response = _runtime_setting_reply(user_text, detected_lang)
        session_repository.record_session_state(
            session_id=session_id, emotion="",
            user_speech=user_text, ai_response=ai_response,
            language=detected_lang
        )
        audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
        return {
            "status": "success",
            "mode": "runtime_setting",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": audio_base64,
            "mentioned_ids": [],
            "cart_actions": [],
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "dialogue": _dialogue(user_text, ai_response, detected_lang),
            "citations": [],
            "retrieval_evaluation": {"sufficient": True, "reason": "runtime_setting"},
            "rag_debug": {"route": route},
            "trigger_recommend": False
        }

    if route.get("intent") == "unknown":
        ai_response = (
            "I can currently help with ordering, menu recommendations, operation guidance, and prepared RAG documents."
            if detected_lang == "en"
            else "我目前只能協助點餐、菜單推薦、操作說明與已建立的 RAG 文件內容。"
        )
        audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
        return {
            "status": "success",
            "mode": "unknown",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": audio_base64,
            "mentioned_ids": [],
            "cart_actions": [],
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "dialogue": _dialogue(user_text, ai_response, detected_lang),
            "citations": [],
            "retrieval_evaluation": {"sufficient": False, "reason": "unknown_intent"},
            "rag_debug": {"route": route},
            "trigger_recommend": False
        }

    rag_details = await asyncio.to_thread(rag_service.retrieve_with_retry, user_text)
    global_context = await asyncio.to_thread(database.get_global_rag_context)
    if global_context:
        rag_details["context"] = "\n\n".join(
            part for part in [global_context, rag_details.get("context", "").strip()] if part
        )
    rag_context = rag_details.get("context", "")
    is_sufficient = rag_service.is_context_sufficient(rag_details)
    if not is_sufficient:
        ai_response = (
            "The current documents do not contain enough information to answer. Please add the corresponding RAG document or confirm the setting."
            if detected_lang == "en"
            else "目前文件沒有足夠資訊回答，請新增對應 RAG 文件或確認設定。"
        )
        session_repository.record_session_state(
            session_id=session_id, emotion="",
            user_speech=user_text, ai_response=ai_response,
            language=detected_lang
        )
        audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)
        return {
            "status": "success",
            "mode": "rag_question",
            "user_text": user_text,
            "ai_response": ai_response,
            "audio_base64": audio_base64,
            "mentioned_ids": [],
            "cart_actions": [],
            "detected_lang": detected_lang,
            "raw_detected_lang": stt_result.get("raw_language", ""),
            "dialogue": _dialogue(user_text, ai_response, detected_lang),
            "citations": rag_details.get("citations", []),
            "retrieval_evaluation": rag_details.get("evaluation", {}),
            "rag_debug": {
                "route": route,
                "quality_gate": rag_details.get("quality_gate"),
                "retrieval_evaluation": rag_details.get("evaluation"),
                "citations": rag_details.get("citations"),
                "verification": None,
            },
            "trigger_recommend": False
        }
    qa_provider = str(config.get("QA_AI_PROVIDER", "ollama") or "ollama").lower()
    source_rule = (
        "Gemini 回覆不需要在 ai_response 說明來源、引用 file_name、page 或 chunk_id。\n"
        if qa_provider == "gemini"
        else (
            "如果實際使用 RAG 補充內容回答，才在 ai_response 末尾附上來源 file_name、page、chunk_id；"
            "若本次沒有可用 RAG，請不要輸出 RAG 不足或要求新增 RAG。\n"
        )
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
        "如果顧客是在直接點餐，例如說「我要一個大麥克」、「加一份薯條」，請在 JSON 加上 cart_actions。\n"
        "如果顧客表示很急、趕時間、要很快做好的餐點，請根據完整菜單白名單中的製作時間篩選較快完成的餐點。\n"
        "cart_actions 格式固定為 [{\"action\":\"add\",\"id\":\"菜單ID\",\"quantity\":數量}]；id 必須來自完整菜單白名單，quantity 介於 1 到 10。\n"
        "如果只是詢問或推薦，cart_actions 請輸出空陣列。"
    )
    
    rag_settings = rag_details.get("settings", {})

    async with ollama_semaphore:
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

    verification = None
    if rag_settings.get("answer_verification", True) and "error" not in ask_result:
        verification_context = full_menu_context + "\n\n" + rag_context
        verification = await loop.run_in_executor(
            None,
            rag_service.verify_claims_grounding,
            user_text,
            ask_result.get("ai_response", ""),
            verification_context
        )
        if not verification.get("grounded", True):
            ask_result["ai_response"] = verification.get("safe_answer", "目前資料庫沒有足夠資訊回答這個問題。")
            ask_result["mentioned_ids"] = []
            ask_result["cart_actions"] = []


    fallback_response = (
        "You can ask for a recommendation or say an item directly, for example: I want a Big Mac."
        if detected_lang == "en"
        else "我可以協助您點餐、推薦餐點或說明付款方式。請直接說想點的餐點，例如「我要一個大麥克」。"
    )
    has_error = "error" in ask_result
    ai_response = ask_result.get("ai_response", fallback_response) if not has_error else fallback_response

    if has_error:
        mentioned_ids = []
        cart_actions = []
    else:
        menu_ids = [item.get("id") for item in menu_items if item.get("id")]
        raw_ids = ask_result.get("mentioned_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        if not isinstance(raw_ids, list):
            raw_ids = []
        mentioned_ids = [recommendation_service.clean_menu_id(item_id, menu_ids) for item_id in raw_ids]
        mentioned_ids = [item_id for item_id in mentioned_ids if item_id]
        cart_actions = recommendation_service.coerce_cart_actions(
            ask_result.get("cart_actions", []), user_text, menu_items
        )

    ai_response = recommendation_service.fix_ask_reply_for_intent(
        user_text, detected_lang, ai_response, cart_actions, mentioned_ids
    )

    if cart_actions and _should_save_voice_order_to_rag():
        asyncio.create_task(_save_voice_order_rag_doc(
            session_id, user_text, detected_lang, "rag_question", ai_response,
            cart_actions, menu_items, ollama_semaphore, schedule_rag_rebuild
        ))

    session_repository.record_session_state(
        session_id=session_id, emotion="",
        user_speech=user_text, ai_response=ai_response,
        language=detected_lang
    )
    audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)

    return {
        "status": "success",
        "mode": "rag_question",
        "user_text": user_text,
        "ai_response": ai_response,
        "audio_base64": audio_base64,
        "mentioned_ids": mentioned_ids,
        "cart_actions": cart_actions,
        "detected_lang": detected_lang,
        "raw_detected_lang": stt_result.get("raw_language", ""),
        "dialogue": _dialogue(user_text, ai_response, detected_lang),
        "citations": [] if qa_provider == "gemini" else rag_details.get("citations", []),
        "retrieval_evaluation": rag_details.get("evaluation", {}),
        "rag_debug": {
            "route": route,
            "quality_gate": rag_details.get("quality_gate"),
            "retrieval_evaluation": rag_details.get("evaluation"),
            "citations": rag_details.get("citations"),
            "verification": verification,
        },
        "trigger_recommend": not bool(cart_actions)
    }
