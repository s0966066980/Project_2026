import asyncio
import json
import re
import time

import ai_services
import config
from utils.text_utils import has_cjk, latin_noise_count, remove_latin_noise, to_traditional_lite


EMOTION_LABELS = [
    "未偵測到顧客", "平靜", "開心", "疲憊", "猶豫", "困惑",
    "焦躁", "生氣", "難過", "驚訝", "無法判斷",
]

EMOTION_DISPLAY_BY_LABEL = {
    "未偵測到顧客": "未偵測到顧客：畫面中沒有明確人臉，暫停情緒判斷。",
    "平靜": "平靜：顧客狀態穩定，可正常提供協助。",
    "開心": "開心：顧客情緒正向，可維持輕鬆互動。",
    "疲憊": "疲憊：顧客可能需要快速、直接的點餐協助。",
    "猶豫": "猶豫：顧客可能還在選擇，可提供簡短推薦。",
    "困惑": "困惑：顧客可能不清楚操作，可主動說明流程。",
    "焦躁": "焦躁：顧客可能等候不耐，建議簡短安撫並加快處理。",
    "生氣": "生氣：顧客情緒偏高，建議先安撫並轉客服處理。",
    "難過": "難過：顧客情緒低落，建議用溫和語氣協助。",
    "驚訝": "驚訝：顧客反應明顯，建議確認需求後再推薦。",
    "無法判斷": "無法判斷：目前影像不足，先依語音內容協助。",
}

EMOTION_EN_TO_ZH = {
    "no person": "未偵測到顧客",
    "no customer": "未偵測到顧客",
    "empty": "未偵測到顧客",
    "neutral": "平靜",
    "calm": "平靜",
    "peaceful": "平靜",
    "happy": "開心",
    "joy": "開心",
    "smile": "開心",
    "tired": "疲憊",
    "fatigue": "疲憊",
    "hesitant": "猶豫",
    "uncertain": "猶豫",
    "confused": "困惑",
    "puzzled": "困惑",
    "anxious": "焦躁",
    "irritated": "焦躁",
    "angry": "生氣",
    "sad": "難過",
    "surprised": "驚訝",
    "unable": "無法判斷",
    "unknown": "無法判斷",
}


def build_customer_service_rag_text(
    session_id: str,
    user_text: str,
    detected_lang: str,
    emotion_text: str,
    mode: str,
    customer_reply: str,
    staff_summary: str,
    priority: str,
) -> str:
    return (
        "客服問答紀錄\n"
        f"Session: {session_id}\n"
        f"語言: {detected_lang}\n"
        f"情緒分析: {emotion_text}\n"
        f"回覆模式: {mode}\n"
        f"優先級: {priority}\n"
        f"顧客問題: {user_text}\n"
        f"客服回覆: {customer_reply}\n"
        f"客服摘要: {staff_summary}"
    )


def fallback_customer_reply(lang: str) -> str:
    if lang == "en":
        return "Your request has been sent to our service staff. Please wait a moment."
    return "已通知客服人員，請稍候。"


def enforce_customer_language(text: str, lang: str, fallback: str) -> str:
    text = (text or "").strip()
    if not text:
        return fallback
    if lang == "en":
        return text

    replacements = {
        "apologies": "很抱歉",
        "apology": "抱歉",
        "sorry": "抱歉",
        "orders": "餐點",
        "order": "餐點",
        "ordered food": "餐點",
        "food": "餐點",
        "delay": "延遲",
        "delayed": "延遲",
        "ASAP": "盡快",
        "asap": "盡快",
        "service": "服務",
        "staff": "客服人員",
        "customer": "顧客",
    }
    for source in sorted(replacements, key=len, reverse=True):
        text = re.sub(re.escape(source), replacements[source], text, flags=re.IGNORECASE)
    text = " ".join(text.split())

    if not has_cjk(text) or latin_noise_count(text) > 8:
        return fallback
    return text


def is_order_help_question(user_text: str) -> bool:
    text = (user_text or "").lower()
    zh_hit = any(key in text for key in ["怎麼點餐", "如何點餐", "不會點餐", "怎麼點", "如何點", "不知道怎麼點"])
    en_hit = any(key in text for key in ["how to order", "how do i order", "how can i order", "don't know how to order"])
    return zh_hit or en_hit


def order_help_reply(lang: str) -> tuple[str, str]:
    if lang == "en":
        reply = "You can tap the item you want, check it in the cart, adjust the quantity if needed, then press checkout."
        summary = "Customer needs help with ordering steps. Explained item selection, cart check, quantity adjustment, and checkout."
    else:
        reply = "可以的，您先點選想要的餐點，餐點會加入右側購物車；確認數量沒問題後，再按「確認結帳」就可以完成點餐。"
        summary = "顧客詢問如何點餐，已說明點選餐點、加入購物車、確認數量與結帳流程。"
    return reply, summary


def fix_customer_reply_for_intent(user_text: str, lang: str, customer_reply: str, staff_summary: str) -> tuple[str, str]:
    if not is_order_help_question(user_text):
        return customer_reply, staff_summary

    bad_patterns = ["幫助我們", "選擇適合您的菜品嗎", "您能夠幫助我們", "請您能夠"]
    required_patterns = ["點選", "購物車", "結帳"] if lang != "en" else ["tap", "cart", "checkout"]
    needs_fix = any(p in customer_reply for p in bad_patterns)
    needs_fix = needs_fix or not all(p.lower() in customer_reply.lower() for p in required_patterns)
    if needs_fix:
        return order_help_reply(lang)
    return customer_reply, staff_summary


def emotion_label_from_text(text: str) -> str:
    raw = to_traditional_lite(str(text or "")).strip()
    lower = raw.lower()
    for key, label in EMOTION_EN_TO_ZH.items():
        if label == "未偵測到顧客" and key in lower:
            return label
    for label in EMOTION_LABELS:
        if label in raw:
            return label
    for key, label in EMOTION_EN_TO_ZH.items():
        if key in lower:
            return label
    if any(key in raw for key in ["無人", "沒有人", "未偵測", "沒有明確人臉", "沒有顧客"]):
        return "未偵測到顧客"
    if any(key in raw for key in ["平和", "中性", "正常", "穩定"]):
        return "平靜"
    if any(key in raw for key in ["高興", "愉快", "微笑"]):
        return "開心"
    if any(key in raw for key in ["累", "疲勞", "沒精神"]):
        return "疲憊"
    if any(key in raw for key in ["不確定", "遲疑", "不知道", "選不出", "怎麼點"]):
        return "猶豫"
    if any(key in raw for key in ["不懂", "疑惑", "不會", "看不懂"]):
        return "困惑"
    if any(key in raw for key in ["不耐", "急躁", "太慢", "等很久", "趕時間", "快一點"]):
        return "焦躁"
    if "怒" in raw:
        return "生氣"
    if any(key in raw for key in ["低落", "悲傷"]):
        return "難過"
    return "無法判斷"


def emotion_distribution_from_text(text: str, label_hint: str = "") -> dict:
    raw = to_traditional_lite(str(text or ""))
    lower = raw.lower()
    labels = [label for label in EMOTION_LABELS if label != "未偵測到顧客"]
    scores = {label: 4 for label in labels}
    scores["無法判斷"] = 2
    keyword_map = {
        "平靜": ["平靜", "平和", "穩定", "正常", "中性", "neutral", "calm", "relaxed", "peaceful"],
        "開心": ["開心", "高興", "愉快", "微笑", "笑", "happy", "smile", "joy"],
        "疲憊": ["疲憊", "疲勞", "累", "睏", "沒精神", "tired", "fatigue", "sleepy"],
        "猶豫": ["猶豫", "遲疑", "不確定", "思考", "不知道", "選不出", "想一下", "hesitant", "uncertain"],
        "困惑": ["困惑", "疑惑", "不懂", "不會", "看不懂", "怎麼點", "confused", "puzzled"],
        "焦躁": ["焦躁", "不耐", "急躁", "太慢", "等很久", "趕時間", "快一點", "anxious", "irritated", "impatient"],
        "生氣": ["生氣", "憤怒", "怒", "抱怨", "angry"],
        "難過": ["難過", "悲傷", "低落", "sad"],
        "驚訝": ["驚訝", "訝異", "surprised"],
    }
    for label, terms in keyword_map.items():
        for term in terms:
            haystack = lower if re.search(r"[A-Za-z]", term) else raw
            if term in haystack:
                scores[label] += 18
    label = label_hint if label_hint in scores else emotion_label_from_text(raw)
    if label == "未偵測到顧客":
        return {"未偵測到顧客": 100}
    if label in scores:
        scores[label] += 25
    total = sum(scores.values()) or 1
    distribution = {label: int(round(score * 100 / total)) for label, score in scores.items()}
    diff = 100 - sum(distribution.values())
    if label in distribution:
        distribution[label] += diff
    else:
        distribution["無法判斷"] = distribution.get("無法判斷", 0) + diff
    return dict(sorted(distribution.items(), key=lambda item: item[1], reverse=True))


def emotion_evidence_from_text(
    text: str,
    label: str,
    person_check: dict | None = None,
    speech_text: str = "",
    media_signals: dict | None = None,
) -> str:
    if label == "未偵測到顧客":
        return "YOLO11 未偵測到人物框，暫停情緒判斷。"
    speech = remove_latin_noise(to_traditional_lite(speech_text or ""))
    if speech:
        if any(key in speech for key in ["太慢", "等很久", "快一點", "趕時間"]):
            return "語音內容表達等待或速度不滿。"
        if any(key in speech for key in ["不會", "不懂", "怎麼點", "看不懂"]):
            return "語音內容顯示需要操作協助。"
        if any(key in speech for key in ["不知道", "選不出", "想一下"]):
            return "語音內容顯示正在猶豫選擇。"
    signals = media_signals or {}
    if person_check and person_check.get("person_detected") and signals.get("audio_silent"):
        motion_level = signals.get("motion_level")
        if motion_level in ("very_low", "subtle"):
            return "聲音較少且動作幅度小，依可見人物狀態保守判斷。"
        return "聲音較少，改以表情、姿態與動作線索判斷。"
    raw = remove_latin_noise(to_traditional_lite(text or ""))
    if raw and raw not in EMOTION_LABELS and len(raw) <= 48:
        return raw
    if person_check and person_check.get("person_detected"):
        boxes = person_check.get("boxes") or []
        confidence = boxes[0].get("confidence") if boxes else None
        if confidence is not None:
            return f"YOLO11 偵測到人物，信心值 {int(float(confidence) * 100)}%，再依影片語音與表情判斷。"
        return "YOLO11 偵測到人物，再依影片語音與表情判斷。"
    return "依 Emotion-LLaMA 原始描述中的情緒詞與狀態線索判斷。"


def limited_emotion_display(text: str, source: str = "", label_hint: str = "") -> str:
    merged = " ".join([str(label_hint or ""), str(text or ""), str(source or "")])
    label = label_hint if label_hint in EMOTION_LABELS else emotion_label_from_text(merged)
    if label == "未偵測到顧客":
        return EMOTION_DISPLAY_BY_LABEL[label]

    display = remove_latin_noise(to_traditional_lite(text or ""))
    source_without_latin = re.sub(r"[A-Za-z][A-Za-z0-9_/'’.-]*", "", str(text or ""))
    has_source_latin = bool(re.search(r"[A-Za-z]", str(text or "")))
    english_dominant = has_source_latin and not has_cjk(source_without_latin)
    has_latin = bool(re.search(r"[A-Za-z]", display))
    too_long = len(display) > 58
    too_vague = not has_cjk(display) or display in EMOTION_LABELS
    if has_source_latin or english_dominant or has_latin or too_long or too_vague:
        return EMOTION_DISPLAY_BY_LABEL.get(label, EMOTION_DISPLAY_BY_LABEL["無法判斷"])

    if label != "無法判斷" and label not in display:
        display = f"{label}：{display}"
    return display[:58]


def build_emotion_structured(
    emotion_text: str,
    display_text: str = "",
    label_hint: str = "",
    evidence_hint: str = "",
    distribution_hint: dict | None = None,
    person_check: dict | None = None,
    speech_text: str = "",
    media_signals: dict | None = None,
) -> dict:
    source = to_traditional_lite(str(emotion_text or ""))
    speech = to_traditional_lite(str(speech_text or ""))
    combined_source = " ".join([source, f"顧客語音：{speech}" if speech else ""])
    yolo_person_detected = bool((person_check or {}).get("person_detected"))
    label = label_hint if label_hint in EMOTION_LABELS else emotion_label_from_text(" ".join([label_hint, display_text, combined_source]))
    label_overridden_by_speech = False
    label_overridden_by_yolo = False
    if yolo_person_detected and label == "未偵測到顧客":
        speech_label = emotion_label_from_text(speech)
        label = speech_label if speech_label not in ("未偵測到顧客", "無法判斷") else "無法判斷"
        label_overridden_by_yolo = True
    if not yolo_person_detected and label == "未偵測到顧客" and speech:
        speech_label = emotion_label_from_text(speech)
        label = speech_label if speech_label not in ("未偵測到顧客", "無法判斷") else "無法判斷"
        label_overridden_by_speech = True
    if yolo_person_detected and label == "無法判斷" and not speech:
        signals = media_signals or {}
        if signals.get("audio_silent") and signals.get("motion_level") in ("very_low", "subtle", "unknown"):
            label = "平靜"
            label_overridden_by_yolo = True
    if label_hint == "平靜" and speech:
        speech_label = emotion_label_from_text(speech)
        if speech_label not in ("無法判斷", "平靜", "未偵測到顧客"):
            label = speech_label
            label_overridden_by_speech = True
    display = EMOTION_DISPLAY_BY_LABEL[label] if (label_overridden_by_speech or label_overridden_by_yolo) else limited_emotion_display(display_text or source, combined_source, label)
    distribution = distribution_hint if isinstance(distribution_hint, dict) else {}
    clean_distribution = {}
    for key, value in distribution.items():
        clean_key = emotion_label_from_text(str(key))
        if yolo_person_detected and clean_key == "未偵測到顧客":
            clean_key = "無法判斷"
        try:
            clean_distribution[clean_key] = max(0, min(100, int(round(float(value)))))
        except Exception:
            continue
    if yolo_person_detected and "未偵測到顧客" in clean_distribution:
        clean_distribution["無法判斷"] = clean_distribution.get("無法判斷", 0) + clean_distribution.pop("未偵測到顧客")
    if not clean_distribution:
        clean_distribution = emotion_distribution_from_text(combined_source, label)
    evidence = remove_latin_noise(to_traditional_lite(evidence_hint or ""))
    if label_overridden_by_yolo:
        evidence = emotion_evidence_from_text(source, label, person_check, speech, media_signals)
    if not evidence or len(evidence) > 64:
        evidence = emotion_evidence_from_text(source, label, person_check, speech, media_signals)
    return {
        "emotion_label": label,
        "emotion_display": display,
        "emotion_evidence": evidence,
        "emotion_distribution": clean_distribution,
        "speech_text": speech,
        "media_signals": media_signals or {},
    }


async def detect_person_for_emotion(media_path: str, yolo_semaphore=None) -> dict:
    if not config.get("EMOTION_PERSON_CHECK_ENABLED", True):
        return {"available": False, "person_detected": None, "reason": "disabled"}

    async def _detect():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            ai_services.detect_person_in_video,
            media_path,
            8,
            int(config.get("EMOTION_PERSON_MIN_FACE_HITS", 1)),
        )

    if yolo_semaphore:
        async with yolo_semaphore:
            return await _detect()
    return await _detect()


async def emotion_to_structured_display(
    emotion_text: str,
    person_check: dict | None = None,
    speech_text: str = "",
    media_signals: dict | None = None,
    ollama_semaphore=None,
) -> dict:
    source = (emotion_text or "").strip()
    speech = to_traditional_lite(speech_text or "").strip()
    if not source:
        return build_emotion_structured(
            "無法判斷", "尚未取得明確情緒分析。", "無法判斷",
            person_check=person_check, speech_text=speech, media_signals=media_signals,
        )
    system_prompt = (
        "你是智慧 POS 的情緒文字轉換器。\n"
        "請把 Emotion-LLaMA 的影像/音訊分析與 Whisper 語音文字收斂成固定情緒標籤、判斷依據與量化分佈。\n"
        "emotion_label 只能從這些值選一個：未偵測到顧客、平靜、開心、疲憊、猶豫、困惑、焦躁、生氣、難過、驚訝、無法判斷。\n"
        "emotion_display 必須是繁體中文，禁止英文、禁止簡體字，最多 35 個中文字。\n"
        "emotion_evidence 必須是繁體中文，最多 40 個中文字，說明判斷依據；不可只說模型判斷。\n"
        "emotion_distribution 是各情緒可能性百分比，總和必須接近 100；不要全部給平靜。\n"
        "若 YOLO11 人物偵測結果顯示 person_detected=true，禁止輸出「未偵測到顧客」；此時若 Emotion-LLaMA 說未偵測到，請改判「無法判斷」或依語音文字判斷。\n"
        "低音量或沒有辨識到語音，不代表無法判斷；若看得到人物，請改用臉部表情、姿態、手勢、動作幅度與停頓作保守判斷。\n"
        "動作幅度小時，不要當作沒有情緒；若無明顯負面或正向線索，可判斷為低強度平靜，並在 evidence 說明是保守判斷。\n"
        "Whisper 語音文字是重要依據：顧客抱怨速度慢、等很久或催促時，應提高焦躁/生氣；顧客說不會、不懂、怎麼點餐時，應提高困惑；顧客說不知道、選不出時，應提高猶豫。\n"
        "不要描述衣服、背景等無關細節；只保留表情、語氣、動作、語音內容與服務狀態線索。\n"
        "只輸出合法 JSON：{\"emotion_label\":\"平靜\",\"emotion_display\":\"平靜：顧客狀態穩定。\",\"emotion_evidence\":\"語氣穩定且無明顯急躁動作。\",\"emotion_distribution\":{\"平靜\":55,\"猶豫\":20,\"困惑\":10,\"疲憊\":10,\"焦躁\":5}}"
    )
    user_prompt = (
        f"【YOLO11 人物偵測】\n{json.dumps(person_check or {}, ensure_ascii=False)}\n\n"
        f"【音量與動作訊號】\n{json.dumps(media_signals or {}, ensure_ascii=False)}\n\n"
        f"【Emotion-LLaMA 原始分析】\n{source}\n\n"
        f"【Whisper 語音文字】\n{speech or '未辨識到明確語音'}"
    )

    async def _ask():
        loop = asyncio.get_running_loop()
        provider = str(config.get("EMOTION_AI_PROVIDER", config.get("QA_AI_PROVIDER", "ollama")) or "ollama").lower()
        model_name = config.get("GEMINI_MODEL_NAME", "") if provider == "gemini" else config.get("MODEL_NAME", "llama3.2")
        return await loop.run_in_executor(
            None, ai_services.ask_llm, system_prompt, user_prompt, "EMOTION_DISPLAY", model_name, provider
        )

    try:
        if ollama_semaphore:
            async with ollama_semaphore:
                result = await _ask()
        else:
            result = await _ask()
        if "error" in result:
            return build_emotion_structured(source, source, person_check=person_check, speech_text=speech, media_signals=media_signals)
        return build_emotion_structured(
            source,
            result.get("emotion_display", ""),
            result.get("emotion_label", ""),
            result.get("emotion_evidence", ""),
            result.get("emotion_distribution", {}),
            person_check,
            speech,
            media_signals,
        )
    except Exception:
        return build_emotion_structured(source, source, person_check=person_check, speech_text=speech, media_signals=media_signals)


async def emotion_to_traditional_display(emotion_text: str, ollama_semaphore=None) -> str:
    return (await emotion_to_structured_display(emotion_text, ollama_semaphore=ollama_semaphore)).get("emotion_display", "")


async def analyze_customer_emotion(
    session_id: str,
    media_path: str,
    speech_text: str = "",
    emotion_cache: dict | None = None,
    emotion_semaphore=None,
    yolo_semaphore=None,
    ollama_semaphore=None,
) -> str:
    cache = emotion_cache if emotion_cache is not None else {}
    cached = cache.get(session_id)
    wait_sec = float(config.get("CUSTOMER_EMOTION_WAIT_SEC", 8))
    acquired = False
    try:
        loop = asyncio.get_running_loop()
        media_signals = await ai_services.async_analyze_emotion_media_signals(media_path)
        person_check = await detect_person_for_emotion(media_path, yolo_semaphore)
        if (
            person_check.get("available")
            and person_check.get("person_detected") is False
            and not speech_text.strip()
            and media_signals.get("audio_silent", True)
        ):
            emotion_text = "未偵測到顧客，先依語音內容處理。"
            emotion_structured = build_emotion_structured(
                emotion_text, emotion_text, "未偵測到顧客",
                person_check=person_check, speech_text=speech_text, media_signals=media_signals,
            )
            cache[session_id] = {
                "emotion": emotion_text,
                "emotion_display": emotion_structured["emotion_display"],
                "emotion_structured": emotion_structured,
                "no_person": True,
                "person_check": person_check,
                "ts": time.time(),
            }
            return emotion_text

        if emotion_semaphore:
            await asyncio.wait_for(emotion_semaphore.acquire(), timeout=wait_sec)
            acquired = True
        emotion_data = await ai_services.async_get_emotion_from_llama(media_path, speech_text, media_signals)
        emotion_text = emotion_data.get("emotion_raw", "") or "無法辨識具體情緒。"
        if emotion_data.get("emotion_available") is False:
            emotion_structured = build_emotion_structured(
                emotion_text,
                "Emotion-LLaMA 未執行：服務未連線或尚未啟動。",
                "無法判斷",
                evidence_hint="Emotion-LLaMA 服務未連線。",
                person_check=person_check,
                speech_text=speech_text,
                media_signals=media_signals,
            )
            cache[session_id] = {
                "emotion": emotion_text,
                "emotion_display": emotion_structured["emotion_display"],
                "emotion_structured": emotion_structured,
                "no_person": False,
                "person_check": person_check,
                "ts": time.time(),
            }
            return emotion_structured["emotion_display"]
        emotion_structured = await emotion_to_structured_display(
            emotion_text, person_check, speech_text, media_signals, ollama_semaphore
        )
        cache[session_id] = {
            "emotion": emotion_text,
            "emotion_display": emotion_structured["emotion_display"],
            "emotion_structured": emotion_structured,
            "no_person": False,
            "ts": time.time(),
        }
        return emotion_structured["emotion_display"]
    except asyncio.TimeoutError:
        if cached:
            return f"{cached.get('emotion', '')}（使用最近一次情緒快取）"
        return "Emotion-LLaMA 忙線，已先依語音內容處理。"
    except Exception as e:
        if cached:
            return f"{cached.get('emotion', '')}（Emotion-LLaMA 本次失敗，使用快取）"
        return f"Emotion-LLaMA 分析失敗：{e}"
    finally:
        if acquired and emotion_semaphore:
            emotion_semaphore.release()
