import asyncio
import os
import shutil
import time

import ai_services
import config
import database
from repositories import log_repository, menu_repository, session_repository
from services import customer_service
from services import rag_review_service
from services import recommendation_service


async def handle_customer_service(
    session_id: str,
    media_path: str,
    suffix: str,
    multi_lang: bool,
    use_ollama: bool,
    deps: dict,
) -> dict:
    """
    處理客服請求的核心邏輯，回傳完整的 response dict。
    包含：STT、情緒分析、Ollama 客服回覆、語言校正、
    媒體保存、RAG 文件審查、session 紀錄、TTS 生成。
    """
    loop = asyncio.get_running_loop()
    stt_result = await ai_services.async_safe_transcribe_with_language(media_path)
    user_text = stt_result["text"]
    detected_lang = stt_result["language"] if multi_lang else "zh"
    if not user_text.strip():
        return {"status": "error", "message": "無法辨識客服語音內容"}

    emotion_text = await customer_service.analyze_customer_emotion(
        session_id=session_id,
        media_path=media_path,
        speech_text=user_text,
        emotion_cache=deps["emotion_cache"],
        emotion_semaphore=deps["emotion_semaphore"],
        yolo_semaphore=deps["yolo_semaphore"],
        ollama_semaphore=deps["ollama_semaphore"],
    )
    emotion_context = recommendation_service.build_emotion_prompt_context(
        deps["emotion_cache"].get(session_id),
        session_repository.get_session_history(session_id),
    )

    qa_provider = config.get("QA_AI_PROVIDER", "ollama")
    mode = qa_provider if use_ollama else "human"
    mentioned_ids = []

    if use_ollama:
        full_menu_context = await asyncio.to_thread(database.build_full_menu_context)
        rag_context = await asyncio.to_thread(database.retrieve_menu_from_rag, user_text, emotion_text)
        language_contract = (
            "Language contract: the customer used English. customer_reply and staff_summary must be English only."
            if detected_lang == "en"
            else "語言契約：顧客使用中文。customer_reply 與 staff_summary 必須全部使用繁體中文，禁止混入任何英文單字。"
        )
        user_prompt = (
            f"{language_contract}\n\n"
            f"【顧客語音文字】\n{user_text}\n\n"
            f"{emotion_context}\n"
            f"客服情緒摘要: {emotion_text}\n\n"
            f"{full_menu_context}\n\n"
            f"【RAG 補充內容】\n{rag_context}\n\n"
            "重要限制：不可編造不存在的餐點、優惠、政策或已完成的人工作業。\n"
            "客服回覆必須參考 Emotion-LLaMA 的情緒標籤、判斷依據與顧客語音；若顧客焦躁、生氣或表示很急，先簡短安撫，再提供最快可執行的處理或製作時間較短的餐點選項。"
        )
        async with deps["ollama_semaphore"]:
            service_result = await loop.run_in_executor(
                None,
                ai_services.ask_llm,
                config.get("CUSTOMER_SERVICE_SYSTEM_PROMPT"),
                user_prompt,
                "CUSTOMER_SERVICE",
                "",
                qa_provider,
            )
        customer_reply = service_result.get("customer_reply") if "error" not in service_result else ""
        staff_summary = service_result.get("staff_summary") if "error" not in service_result else ""
        priority = service_result.get("priority", "normal") if "error" not in service_result else "normal"
        raw_ollama = service_result.get("_raw_content") or service_result.get("raw_content", "")
        if not customer_reply:
            customer_reply = customer_service.fallback_customer_reply(detected_lang)
        if not staff_summary:
            staff_summary = user_text
        customer_reply = customer_service.enforce_customer_language(
            customer_reply, detected_lang, customer_service.fallback_customer_reply(detected_lang)
        )
        staff_summary = customer_service.enforce_customer_language(
            staff_summary, detected_lang, user_text
        )
        customer_reply, staff_summary = customer_service.fix_customer_reply_for_intent(
            user_text, detected_lang, customer_reply, staff_summary
        )
        raw_ids = service_result.get("mentioned_ids", []) if isinstance(service_result, dict) else []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        menu_items = await asyncio.to_thread(menu_repository.get_menu)
        menu_ids = [item.get("id") for item in menu_items if item.get("id")]
        mentioned_ids = [recommendation_service.clean_menu_id(item_id, menu_ids) for item_id in raw_ids]
        mentioned_ids = [item_id for item_id in mentioned_ids if item_id]
    else:
        customer_reply = customer_service.fallback_customer_reply(detected_lang)
        staff_summary = user_text
        priority = "normal"
        raw_ollama = ""

    source_id = f"cs_{session_id}_{int(time.time())}"
    media_filename = ""
    media_url = ""
    try:
        os.makedirs(config.CUSTOMER_SERVICE_MEDIA_DIR, exist_ok=True)
        safe_suffix = suffix if suffix.startswith(".") and len(suffix) <= 8 else ".webm"
        media_filename = f"{source_id}{safe_suffix}"
        saved_media_path = os.path.join(config.CUSTOMER_SERVICE_MEDIA_DIR, media_filename)
        await asyncio.to_thread(shutil.copyfile, media_path, saved_media_path)
        media_url = f"/api/customer_service_media/{media_filename}"
    except Exception as media_err:
        print(f"⚠️ 客服錄音保存失敗: {media_err}")

    source_text = customer_service.build_customer_service_rag_text(
        session_id=session_id,
        user_text=user_text,
        detected_lang=detected_lang,
        emotion_text=emotion_text,
        mode=mode,
        customer_reply=customer_reply,
        staff_summary=staff_summary,
        priority=priority,
    )
    review_result = await rag_review_service.review_rag_text(
        source_text, "customer_service", source_id, deps["ollama_semaphore"]
    )
    rag_doc = await asyncio.to_thread(
        database.upsert_reviewed_rag_doc,
        "customer_service", source_id, source_text, review_result
    )
    deps["schedule_rag_rebuild"]("customer service RAG doc")
    session_repository.record_session_state(
        session_id=session_id,
        emotion=emotion_text,
        user_speech=user_text,
        ai_response=customer_reply,
        language=detected_lang,
    )
    await asyncio.to_thread(log_repository.append_customer_service_log, {
        "timestamp": time.time(),
        "session_id": session_id,
        "source_id": source_id,
        "rag_doc_id": rag_doc.get("id"),
        "mode": mode,
        "language": detected_lang,
        "raw_language": stt_result.get("raw_language", ""),
        "emotion": emotion_text,
        "user_text": user_text,
        "customer_reply": customer_reply,
        "staff_summary": staff_summary,
        "priority": priority,
        "mentioned_ids": mentioned_ids,
        "ollama_result": raw_ollama,
        "media_filename": media_filename,
        "media_url": media_url,
    })

    audio_base64 = ""
    if use_ollama:
        audio_base64 = await ai_services.generate_tts_audio_base64(
            customer_reply, lang=detected_lang
        )

    return {
        "status": "success",
        "mode": mode,
        "user_text": user_text,
        "detected_lang": detected_lang,
        "raw_detected_lang": stt_result.get("raw_language", ""),
        "emotion": emotion_text,
        "customer_reply": customer_reply,
        "staff_summary": staff_summary,
        "priority": priority,
        "mentioned_ids": mentioned_ids,
        "ollama_result": raw_ollama,
        "rag_doc_id": rag_doc.get("id"),
        "media_url": media_url,
        "audio_base64": audio_base64,
    }
