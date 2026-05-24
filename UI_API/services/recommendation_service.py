import asyncio
from datetime import datetime
import hashlib
import json
import re
import time

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from utils.text_utils import to_traditional_lite


_RECOMMEND_RAG_CACHE = {"ts": 0.0, "context": ""}
_RECOMMEND_RAG_TTL_SEC = 60.0


async def _get_cached_recommend_rag_context() -> str:
    now = time.time()
    cached = _RECOMMEND_RAG_CACHE
    if cached["context"] and now - cached["ts"] < _RECOMMEND_RAG_TTL_SEC:
        return cached["context"]
    context = await asyncio.to_thread(database.retrieve_menu_from_rag, "推薦餐點")
    _RECOMMEND_RAG_CACHE["ts"] = now
    _RECOMMEND_RAG_CACHE["context"] = context
    return context


def _deterministic_variant_score(session_id: str, history_len: int) -> float:
    key = f"{session_id or 'anonymous'}:{history_len}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 1000) / 1000.0


ZH_NUMBERS = {
    "一": 1, "二": 2, "兩": 2, "俩": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

ORDER_TEXT_REPLACEMENTS = {
    "起士": "起司",
    "芝士": "起司",
    "起私": "起司",
    "麥香鷄": "麥香雞",
    "勁辣鷄腿堡": "勁辣雞腿堡",
    "麥克鷄塊": "麥克雞塊",
    "大麥可": "大麥克",
    "大mac": "大麥克",
    "bigmac": "大麥克",
    "big mac": "大麥克",
    "起司堡": "吉事堡",
    "4盎司": "四盎司",
    "魚堡": "麥香魚",
    "中暑": "中薯",
    "大暑": "大薯",
    "薯條": "薯條",
    "中薯": "薯條",
    "大薯": "薯條",
    "數條": "薯條",
    "署條": "薯條",
    "暑條": "薯條",
    "數餅": "薯餅",
    "署餅": "薯餅",
    "zero": "零卡",
    "可口可樂zero": "零卡可樂",
    "可口可樂零卡": "零卡可樂",
    "可樂零卡": "零卡可樂",
    "那堤": "拿鐵",
}


def clean_menu_id(raw_id, menu_ids: list[str]) -> str:
    raw = "".join(ch for ch in str(raw_id or "") if ch.isalnum()).upper()
    for menu_id in menu_ids:
        normalized = "".join(ch for ch in str(menu_id) if ch.isalnum()).upper()
        if raw == normalized or (raw and raw in normalized) or (normalized and normalized in raw):
            return menu_id
    return ""


def parse_quantity(raw: str) -> int:
    text = str(raw or "").strip()
    if not text:
        return 1
    if text.isdigit():
        return max(1, min(10, int(text)))
    return max(1, min(10, ZH_NUMBERS.get(text[0], 1)))


def normalize_order_text(text: str) -> str:
    normalized = to_traditional_lite(str(text or "")).lower()
    normalized = re.sub(r"[\s，,。.!！?？、；;：:「」『』\"'（）()]+", "", normalized)
    for source, target in sorted(ORDER_TEXT_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalized.replace(source.lower(), target.lower())
    return normalized


def menu_aliases(item: dict) -> list[str]:
    name = str(item.get("name") or "")
    aliases = {name, name.replace(" ", "")}
    for alias in item.get("aliases") or []:
        aliases.add(str(alias))
    category = str(item.get("category") or "")
    category_aliases = {
        "早餐": ["早餐"],
        "飲料": ["飲料", "喝的"],
        "McCafé": ["咖啡", "mcafe", "mccafe"],
        "McCafé®": ["咖啡", "mcafe", "mccafe"],
        "點心": ["點心", "小點"],
    }
    for alias in category_aliases.get(category, []):
        aliases.add(alias)
    if len(name) >= 4:
        aliases.add(name[-4:])
    if len(name) >= 2:
        aliases.add(name[-2:])
    return [normalize_order_text(alias) for alias in aliases if normalize_order_text(alias)]


def extract_quantity_for_alias(text: str, alias: str) -> int:
    qty_group = r"(\d+|一|二|兩|俩|三|四|五|六|七|八|九|十)"
    unit = r"(?:份|個|杯|碗|道|組)?"
    patterns = [
        rf"{qty_group}\s*{unit}\s*{re.escape(alias)}",
        rf"{re.escape(alias)}\s*{qty_group}\s*{unit}",
    ]
    for pattern in patterns:
        hit = re.search(pattern, text)
        if hit:
            return parse_quantity(hit.group(1))
    return 1


def looks_like_order_request(text: str) -> bool:
    lowered = normalize_order_text(text)
    keywords = [
        "我要", "我想", "想吃", "想喝", "幫我加", "加一", "加兩", "加2", "點一",
        "點兩", "點", "來一", "來兩", "來", "一份", "兩份", "2份", "全部",
        "都點", "全點", "每個", "每樣", "order", "add", "iwant", "all",
    ]
    qty_unit = r"(\d+|一|二|兩|俩|三|四|五|六|七|八|九|十)(份|個|杯|碗|道|組)"
    return any(key in lowered for key in keywords) or bool(re.search(qty_unit, lowered))


def looks_like_all_order_request(text: str) -> bool:
    normalized = normalize_order_text(text)
    patterns = ["全部餐點", "全部都點", "全部點", "都點", "全點", "每個餐點", "每樣", "allitems", "ordereverything"]
    return looks_like_order_request(normalized) and any(pattern in normalized for pattern in patterns)


def answer_menu_question_from_text(user_text: str, menu_items: list[dict]) -> dict:
    normalized = normalize_order_text(user_text)
    if not normalized or not menu_items:
        return {}

    def item_text(item: dict) -> str:
        aliases = "".join(str(alias or "") for alias in item.get("aliases") or [])
        return normalize_order_text(f"{item.get('name', '')}{item.get('category', '')}{aliases}")

    def item_price(item: dict) -> int:
        try:
            return int(float(item.get("price", 0)))
        except Exception:
            return 0

    def prep_time(item: dict) -> int:
        try:
            return int(float(item.get("prep_time_minutes", item.get("prep_minutes", 99))))
        except Exception:
            return 99

    candidates = [item for item in menu_items if item.get("id") and item.get("name")]
    if any(key in normalized for key in ["最快", "很快", "快做好", "趕時間"]):
        candidates = sorted(candidates, key=lambda item: (prep_time(item), item_price(item)))
        if candidates:
            top = candidates[0]
            minutes = prep_time(top)
            return {
                "ai_response": f"最快可以考慮{top.get('name')}，預估製作約 {minutes} 分鐘，價格 ${item_price(top)}。",
                "mentioned_ids": [top.get("id")],
            }

    if any(key in normalized for key in ["雞肉", "雞", "鷄", "chicken"]) and any(key in normalized for key in ["推薦", "有什麼", "想吃"]):
        chicken_items = [item for item in candidates if any(key in item_text(item) for key in ["雞", "鷄", "chicken"])]
        if any(key in normalized for key in ["不要辣", "不辣", "不吃辣"]):
            chicken_items = [item for item in chicken_items if "辣" not in item_text(item)]
        chicken_items = sorted(chicken_items, key=lambda item: (prep_time(item), item_price(item)))
        if chicken_items:
            top = chicken_items[0]
            return {
                "ai_response": f"雞肉品項可以考慮{top.get('name')}，這是菜單上的餐點，價格 ${item_price(top)}。",
                "mentioned_ids": [top.get("id")],
            }

    if any(key in normalized for key in ["飲料", "喝", "可樂", "咖啡", "拿鐵", "甜點", "drink", "coffee"]) and any(key in normalized for key in ["推薦", "有什麼", "想喝", "可以"]):
        drink_items = [
            item for item in candidates
            if any(key in item_text(item) for key in ["飲料", "咖啡", "café", "cafe", "可樂", "雪碧", "茶", "拿鐵"])
        ]
        drink_items = sorted(drink_items, key=lambda item: (prep_time(item), item_price(item)))
        if drink_items:
            top = drink_items[0]
            return {
                "ai_response": f"飲料可以考慮{top.get('name')}，這是菜單上的品項，價格 ${item_price(top)}。",
                "mentioned_ids": [top.get("id")],
            }

    if any(key in normalized for key in ["不要辣", "不辣", "不吃辣"]) and any(key in normalized for key in ["推薦", "有什麼", "可以點"]):
        mild_items = [item for item in candidates if "辣" not in item_text(item)]
        mild_items = sorted(mild_items, key=lambda item: (prep_time(item), item_price(item)))
        if mild_items:
            top = mild_items[0]
            return {
                "ai_response": f"不吃辣可以考慮{top.get('name')}，價格 ${item_price(top)}。",
                "mentioned_ids": [top.get("id")],
            }

    if any(key in normalized for key in ["便宜", "最便宜", "省錢", "低價"]):
        cheap_items = sorted(candidates, key=lambda item: (item_price(item), prep_time(item)))
        if cheap_items:
            top = cheap_items[0]
            return {
                "ai_response": f"想省一點可以考慮{top.get('name')}，價格 ${item_price(top)}。",
                "mentioned_ids": [top.get("id")],
            }

    menu_hint_terms = ["薯條", "早餐", "咖啡", "可樂", "漢堡", "牛肉", "魚", "雞塊", "點心"]
    matched_items = [
        item for item in candidates
        if any(term in normalized and term in item_text(item) for term in menu_hint_terms)
    ]
    if matched_items and any(key in normalized for key in ["推薦", "有什麼", "可以", "想吃", "想喝"]):
        matched_items = sorted(matched_items, key=lambda item: (prep_time(item), item_price(item)))
        top = matched_items[0]
        return {
            "ai_response": f"可以考慮{top.get('name')}，這是菜單上的品項，價格 ${item_price(top)}。",
            "mentioned_ids": [top.get("id")],
        }

    if any(key in normalized for key in ["推薦", "有什麼", "吃什麼", "喝什麼", "recommend"]):
        candidates = sorted(candidates, key=lambda item: (prep_time(item), item_price(item)))
        if candidates:
            top = candidates[0]
            return {
                "ai_response": f"可以先參考{top.get('name')}，這是目前菜單上的品項，價格 ${item_price(top)}。",
                "mentioned_ids": [top.get("id")],
            }

    return {}


def fallback_cart_actions_from_text(user_text: str, menu_items: list[dict]) -> list[dict]:
    text = normalize_order_text(user_text)
    if not looks_like_order_request(text):
        return []
    if looks_like_all_order_request(text):
        return [
            {"action": "add", "id": item.get("id"), "quantity": 1}
            for item in menu_items
            if item.get("id")
        ]
    actions = []
    for item in menu_items:
        for alias in menu_aliases(item):
            if alias and alias in text:
                actions.append({
                    "action": "add",
                    "id": item.get("id"),
                    "quantity": extract_quantity_for_alias(text, alias),
                })
                break
    return actions


def coerce_cart_actions(raw_actions, user_text: str, menu_items: list[dict]) -> list[dict]:
    menu_ids = [item.get("id") for item in menu_items if item.get("id")]
    actions = raw_actions if isinstance(raw_actions, list) else []
    cleaned = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        menu_id = clean_menu_id(action.get("id") or action.get("menu_id") or action.get("item_id"), menu_ids)
        if not menu_id:
            continue
        qty = action.get("quantity", action.get("qty", 1))
        try:
            qty = int(qty)
        except Exception:
            qty = parse_quantity(str(qty))
        qty = max(1, min(10, qty))
        existing = next((row for row in cleaned if row["id"] == menu_id), None)
        if existing:
            existing["quantity"] = max(existing["quantity"], qty)
        else:
            cleaned.append({"action": "add", "id": menu_id, "quantity": qty})
    if cleaned:
        return cleaned
    return fallback_cart_actions_from_text(user_text, menu_items)


def coerce_recommendation(
    result: dict,
    variant: str,
    menu_ids: list[str],
    excluded_ids: set[str] | None = None,
    menu_items: list[dict] | None = None,
) -> dict:
    if isinstance(result, list):
        first_dict = next((row for row in result if isinstance(row, dict)), {})
        result = first_dict
    elif not isinstance(result, dict):
        result = {}
    excluded_ids = excluded_ids or set()
    source_error = "error" in result
    raw_ids = result.get("recommendation_ids") or result.get("recommendation_id") or []
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    if not isinstance(raw_ids, list):
        raw_ids = []

    cleaned = []
    for raw_id in raw_ids:
        menu_id = clean_menu_id(raw_id, menu_ids)
        if menu_id and menu_id not in cleaned:
            cleaned.append(menu_id)

    if not cleaned or (excluded_ids and set(cleaned).issubset(excluded_ids)):
        fallback = next((mid for mid in menu_ids if mid not in excluded_ids), menu_ids[0] if menu_ids else "")
        cleaned = [fallback] if fallback else []

    if variant == "A":
        cleaned = cleaned[:1]
    elif variant == "B":
        cleaned = cleaned[:3]

    reason = (
        result.get("reason")
        or result.get("empathy_response")
        or ("從另一個角度為您挑選這組餐點。" if variant == "B" else "這是根據您當下狀態為您挑選的餐點。")
    )
    reason = align_recommendation_reason(reason, cleaned, variant, menu_items or [])
    aligned_result = {
        "recommendation_ids": cleaned,
        "reason": reason,
        "variant": variant,
    }
    return {
        "recommendation_ids": cleaned,
        "reason": reason,
        "ollama_result": json.dumps(aligned_result, ensure_ascii=False),
        "variant": variant,
        "error": source_error and not cleaned,
        "source_error": source_error,
    }


def align_recommendation_reason(
    reason: str,
    recommendation_ids: list[str],
    variant: str,
    menu_items: list[dict],
) -> str:
    """讓顧客看到的推播文字永遠對齊最終白名單校正後的餐點。"""
    reason = to_traditional_lite(str(reason or "")).strip()
    name_by_id = {
        str(item.get("id")): str(item.get("name") or "").strip()
        for item in menu_items
        if item.get("id") and item.get("name")
    }
    selected_names = [name_by_id.get(str(menu_id), "") for menu_id in recommendation_ids]
    selected_names = [name for name in selected_names if name]
    if not selected_names:
        return reason or "這是根據您當下狀態為您挑選的餐點。"
    selected_items = [
        item for item in menu_items
        if str(item.get("id")) in set(recommendation_ids)
    ]

    selected_id_set = set(recommendation_ids)
    other_names = [
        str(item.get("name") or "").strip()
        for item in menu_items
        if item.get("id") not in selected_id_set and item.get("name")
    ]
    mentions_selected = any(name and name in reason for name in selected_names)
    mentions_other = any(name and name in reason for name in other_names)

    if not reason or mentions_other:
        if variant == "B" and len(selected_names) > 1:
            return build_recommendation_copy(selected_items, variant)
        return build_recommendation_copy(selected_items, variant)

    if not mentions_selected:
        return build_recommendation_copy(selected_items, variant)
    generic_reason = len(reason) < 42 or any(key in reason for key in ["比較符合現在", "當下狀態", "經典", "推薦您試試"])
    if generic_reason:
        return build_recommendation_copy(selected_items, variant)
    return reason


def build_recommendation_copy(selected_items: list[dict], variant: str) -> str:
    items = [item for item in selected_items if item.get("name")]
    if not items:
        return "這份餐點會比較符合現在的需求。"
    if variant == "B" and len(items) > 1:
        names = "、".join(str(item.get("name")) for item in items[:3])
        total = sum(int(float(item.get("price") or 0)) for item in items[:3])
        return f"如果想一次點得完整，{names} 很適合放在一起；有主餐也有搭配品，合計約 ${total}。"
    item = items[0]
    name = str(item.get("name") or "")
    price = int(float(item.get("price") or 0))
    desc = str(item.get("description") or "").strip()
    if desc:
        desc = re.sub(r"\s+", "，", desc).strip("，。、,. ")[:34]
        return f"如果想快速決定，可以先選{name}；{desc}，價格 ${price}。"
    return f"如果想快速決定，可以先選{name}；點餐簡單、接受度高，價格 ${price}。"


def history_signature(history: list, ab_mode: str) -> str:
    compact = []
    for record in history[-6:]:
        compact.append({
            "emotion": record.get("emotion", ""),
            "user_speech": record.get("user_speech") or record.get("speech", ""),
            "ai_response": record.get("ai_response", ""),
            "language": record.get("language", ""),
        })
    raw = json.dumps({"mode": ab_mode, "history": compact}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_emotion_prompt_context(cached_emotion: dict | None, history: list | None = None) -> str:
    history = history or []
    if cached_emotion and not cached_emotion.get("no_person"):
        structured = cached_emotion.get("emotion_structured") or {}
        display = cached_emotion.get("emotion_display") or cached_emotion.get("emotion") or ""
        label = structured.get("emotion_label", "")
        evidence = structured.get("emotion_evidence", "")
        distribution = structured.get("emotion_distribution", {})
        return (
            "【當前 Emotion-LLaMA 情緒分析】\n"
            f"顯示: {display}\n"
            f"標籤: {label}\n"
            f"判斷依據: {evidence}\n"
            f"量化分佈: {json.dumps(distribution, ensure_ascii=False)}"
        )
    recent_emotion = next((row.get("emotion") for row in reversed(history) if row.get("emotion")), "")
    if recent_emotion:
        return f"【最近一次情緒紀錄】\n{recent_emotion}"
    return "【當前 Emotion-LLaMA 情緒分析】\n未取得可用情緒分析；請只根據語音、歷史紀錄與菜單推薦。"


def build_combined_ab_prompt(prompt_a: str, prompt_b: str) -> str:
    return (
        "你是一個 A/B 推播實驗控制器，必須一次產生兩個不同推薦版本。\n\n"
        "【A 版策略】\n"
        f"{prompt_a}\n\n"
        "【B 版策略】\n"
        f"{prompt_b}\n\n"
        "請同時輸出 A 版與 B 版。A 版只能推薦 1 個餐點；B 版必須根據歷史點餐紀錄推薦 2~3 個適合搭配的餐點。\n"
        "所有 recommendation_ids 都必須來自【完整菜單白名單】，禁止創造餐點。\n"
        "reason 必須是給顧客直接看的自然口語短句，不要出現「推薦理由」、「A版」、「B版」或系統分析語氣。\n"
        "輸出只能是合法 JSON，格式如下：\n"
        "{\n"
        "  \"variant_a\": {\"recommendation_ids\": [\"餐點ID\"], \"reason\": \"自然口語推薦短句\"},\n"
        "  \"variant_b\": {\"recommendation_ids\": [\"餐點ID1\", \"餐點ID2\"], \"reason\": \"自然口語搭配短句\"}\n"
        "}"
    )


def store_recommend_cache(cache: dict, cache_key: str, data: dict, ts: float):
    cache[cache_key] = {"ts": ts, "data": data}
    while len(cache) > 64:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key, None)


async def generate_recommendation(
    session_id: str,
    ab_mode: str,
    emotion_cache: dict,
    ollama_semaphore,
    emotion_influence: bool = True,
) -> dict:
    """
    核心推薦邏輯，包含：
    1. 取得 session history
    2. 建構 user_prompt（emotion_context、history_str、experiences、pairing_context、menu_context、rag_context）
    3. A/B 或 single 分支的 Ollama 呼叫
    4. coerce_recommendation 白名單校正
    回傳完整的 response_data dict（不含 cache 操作）。
    """
    history = session_repository.get_session_history(session_id)
    history_str = "\n".join([
        f"[{r.get('timestamp','')}] "
        + (f"情緒:{r.get('emotion','')} " if r.get("emotion") else "")
        + (f"顧客說:{r.get('user_speech','') or r.get('speech','')} "
           if (r.get("user_speech") or r.get("speech")) else "")
        for r in history[-8:]
    ]).strip() or "顧客剛開始點餐，尚無紀錄。"

    experiences = await asyncio.to_thread(database.get_successful_experiences)
    pairing_context = await asyncio.to_thread(database.get_order_pairing_context)
    full_menu_context = await asyncio.to_thread(database.build_full_menu_context)
    rag_context = await _get_cached_recommend_rag_context()
    current_emotion = emotion_cache.get(session_id)
    emotion_context = (
        build_emotion_prompt_context(current_emotion, history)
        if emotion_influence and config.get("EMOTION_INFLUENCE_RECOMMEND", True)
        else "【Emotion-LLaMA 情緒分析】本次推薦不使用情緒分析作為依據。"
    )
    user_prompt = (
        f"{emotion_context}\n\n"
        f"【顧客近期狀態與對話】\n{history_str}\n\n"
        f"{experiences}\n\n"
        f"{pairing_context}\n\n"
        f"{full_menu_context}\n\n"
        f"【RAG 補充內容】\n{rag_context}\n\n"
        "重要限制：只能輸出完整菜單白名單存在的餐點 ID；reason 也只能提到真實菜單品項。\n"
        "若【RAG 全域規則】要求 reason 使用固定開頭、語氣或禁用文字，必須直接套用在 reason。\n"
        "若 Emotion-LLaMA 情緒分析可用，推薦必須優先根據該情緒、判斷依據與量化分佈調整；焦躁、急迫或顧客表示趕時間時，優先推薦製作時間較短的餐點。"
    )

    base_prompt = config.get("RECOMMEND_SYSTEM_PROMPT")
    prompt_b_base = config.get("RECOMMEND_SYSTEM_PROMPT_B")
    menu_items = await asyncio.to_thread(menu_repository.get_menu)
    menu_ids = [item.get("id") for item in menu_items if item.get("id")]
    loop = asyncio.get_running_loop()

    if ab_mode == "ab":
        prompt_a = base_prompt
        prompt_b = prompt_b_base

        if config.get("AB_SINGLE_CALL", True):
            combined_prompt = build_combined_ab_prompt(prompt_a, prompt_b)
            async with ollama_semaphore:
                combined = await loop.run_in_executor(
                    None, ai_services.ask_ollama, combined_prompt, user_prompt, "AB"
                )
            if isinstance(combined, list):
                combined = next((row for row in combined if isinstance(row, dict)), {})
            elif not isinstance(combined, dict):
                combined = {}
            result_a = combined.get("variant_a", {}) if "error" not in combined else combined
            result_b = combined.get("variant_b", {}) if "error" not in combined else combined
            if not isinstance(result_a, dict):
                result_a = {}
            if not isinstance(result_b, dict):
                result_b = {}
            if "error" not in combined:
                raw_content = combined.get("_raw_content", json.dumps(combined, ensure_ascii=False))
                result_a["_raw_content"] = raw_content
                result_b["_raw_content"] = raw_content
        else:
            async with ollama_semaphore:
                result_a = await loop.run_in_executor(
                    None, ai_services.ask_ollama, prompt_a, user_prompt, "A"
                )
                result_b = await loop.run_in_executor(
                    None, ai_services.ask_ollama, prompt_b, user_prompt, "B"
                )

        rec_a = coerce_recommendation(result_a, "A", menu_ids, menu_items=menu_items)
        rec_b = coerce_recommendation(
            result_b,
            "B",
            menu_ids,
            excluded_ids=set(rec_a["recommendation_ids"]),
            menu_items=menu_items,
        )

        return {
            "status": "success",
            "mode": "ab",
            "variant_a": rec_a,
            "variant_b": rec_b,
        }

    diversity_ratio = float(config.get("RECOMMEND_DIVERSITY_RATIO", 0.4))
    use_diversity = _deterministic_variant_score(session_id, len(history)) < diversity_ratio
    prompt = prompt_b_base if use_diversity else base_prompt
    variant = "B" if use_diversity else "A"
    async with ollama_semaphore:
        recommendation = await loop.run_in_executor(
            None, ai_services.ask_ollama, prompt, user_prompt, variant
        )

    if isinstance(recommendation, list):
        recommendation = next((row for row in recommendation if isinstance(row, dict)), {})
    elif not isinstance(recommendation, dict):
        recommendation = {}

    if "error" in recommendation:
        return {
            "status": "error",
            "message": recommendation["error"],
            "raw_content": recommendation.get("raw_content", ""),
        }

    rec = coerce_recommendation(recommendation, variant, menu_ids, menu_items=menu_items)
    return {
        "status": "success",
        "mode": "single",
        "recommendation_ids": rec["recommendation_ids"],
        "reason": rec["reason"],
        "variant": variant,
        "ollama_result": rec["ollama_result"],
    }


def fix_ask_reply_for_intent(user_text: str, lang: str, reply: str, cart_actions: list, mentioned_ids: list) -> str:
    """避免模型在不確定時把顧客問句原樣丟回去。"""
    clean_user = re.sub(r"\s+", "", to_traditional_lite(user_text or "").strip()).lower()
    clean_reply = re.sub(r"\s+", "", to_traditional_lite(reply or "").strip()).lower()
    if not clean_reply:
        return "I can help recommend a main dish or drink from the menu." if lang == "en" else "我可以協助您從菜單中推薦主餐或飲品。"
    if cart_actions:
        no_item_phrases = ["菜單沒有", "沒有這個品項", "沒有在菜單", "找不到", "目前菜單沒有"]
        if lang != "en" and any(phrase in clean_reply for phrase in no_item_phrases):
            return ""
        return reply
    if mentioned_ids:
        return reply

    repeated = clean_user and (
        clean_reply == clean_user
        or clean_reply in clean_user
        or clean_user in clean_reply
    )
    vague_zh = any(key in clean_user for key in ["不知道", "不確定", "推薦什麼", "吃什麼", "怎麼點", "不會點"])
    vague_en = any(key in clean_user for key in ["recommend", "whattoeat", "howtoorder", "don'tknow", "notsure"])
    if repeated or (lang != "en" and vague_zh and len(clean_reply) < 18):
        return "我可以協助您從菜單中推薦主餐或飲品，也可以直接說出想點的餐點名稱。"
    if lang == "en" and vague_en and len(clean_reply) < 24:
        return "I can recommend a main dish or drink from the menu, or you can say the item you want to order."
    return reply


def build_checkout_log_entry(
    session_id: str,
    pushed_ids: list,
    cart_ids: list,
    session_history: list,
    pushed_variants: dict | None = None
) -> dict:
    """
    評估一次結帳中的推播成效。
    Repository 只負責保存此函式產出的最終 dict。
    """
    unique_pushed = list(set(pushed_ids))
    pushed_variants = pushed_variants or {}
    cart_id_set = set(cart_ids)
    is_success = bool(set(unique_pushed) & cart_id_set)

    variant_success = {}
    for variant, ids in pushed_variants.items():
        if isinstance(ids, list):
            unique_variant_ids = list(set(ids))
            variant_success[variant] = {
                "pushed_ids": unique_variant_ids,
                "is_success": bool(set(unique_variant_ids) & cart_id_set)
            }

    emotions = list(set(h["emotion"] for h in session_history if h.get("emotion")))
    emotions_summary = ", ".join(emotions) if emotions else "未知"
    speeches = [h["user_speech"] for h in session_history if h.get("user_speech")][-3:]
    languages = list(set(h["language"] for h in session_history if h.get("language")))

    return {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "emotions_summary": emotions_summary,
        "speech_summary": " / ".join(speeches) if speeches else "",
        "languages": languages,
        "pushed_ids": unique_pushed,
        "pushed_variants": pushed_variants,
        "variant_success": variant_success,
        "final_cart_ids": cart_ids,
        "is_success": is_success
    }
