import re
from datetime import datetime

from utils.text_utils import to_traditional_lite



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
        "McCafé": ["咖啡", "mcafe", "mccafe"],
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
    return looks_like_order_request(text) and any(pattern in normalized for pattern in patterns)


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


def _is_recommendation_query(text: str) -> bool:
    """推薦／問答問句 → 不應觸發 fallback 加購邏輯。
    但若同時含加購意圖（「把推薦的加入購物車」「幫我加你推薦的」），則不視為推薦問句。
    """
    _add_intent = [
        "加入購物車", "幫我加", "我要那個", "加進去", "加購", "來一份",
        "點那個", "幫我點", "幫我來", "add to cart", "add it", "add the",
    ]
    lowered = text.lower()
    # 有明確加購意圖 → 優先視為加購請求，不攔截
    if any(k in lowered for k in _add_intent):
        return False
    keywords = [
        "推薦", "建議", "有什麼好", "什麼好吃", "什麼推薦", "你們有什麼",
        "有沒有推薦", "幫我推薦", "介紹", "有什麼特別", "什麼比較好",
        "recommend", "suggest", "what's good", "what do you recommend",
    ]
    return any(k in lowered for k in keywords)


def coerce_cart_actions(raw_actions, user_text: str, menu_items: list[dict]) -> list[dict]:
    # 推薦問句最優先：無論 LLM 輸出什麼 cart_actions 都不加購
    if _is_recommendation_query(user_text):
        return []

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
    # 推薦／問答問句不走 fallback，避免把推薦品項誤加入購物車
    if _is_recommendation_query(user_text):
        return []
    return fallback_cart_actions_from_text(user_text, menu_items)



def build_checkout_log_entry(
    session_id: str,
    pushed_ids: list,
    cart_ids: list,
    cart_items: list | None,
    session_history: list,
) -> dict:
    """
    評估一次結帳中的推播成效。
    Repository 只負責保存此函式產出的最終 dict。
    """
    unique_pushed = list(set(pushed_ids))
    cart_id_set = set(cart_ids)
    is_success = bool(set(unique_pushed) & cart_id_set)

    emotions = list(set(h["emotion"] for h in session_history if h.get("emotion")))
    emotions_summary = ", ".join(emotions) if emotions else "未知"
    speeches = [h["user_speech"] for h in session_history if h.get("user_speech")][-3:]
    languages = list(set(h["language"] for h in session_history if h.get("language")))
    voice_turns = [
        {"user": h.get("user_speech", ""), "ai": h.get("ai_response", "")}
        for h in session_history
        if h.get("user_speech") or h.get("ai_response")
    ]

    return {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "emotions_summary": emotions_summary,
        "speech_summary": " / ".join(speeches) if speeches else "",
        "languages": languages,
        "pushed_ids": unique_pushed,
        "final_cart_ids": cart_ids,
        "final_cart_items": cart_items if isinstance(cart_items, list) else [],
        "is_success": is_success,
        "voice_turns": voice_turns,
    }
