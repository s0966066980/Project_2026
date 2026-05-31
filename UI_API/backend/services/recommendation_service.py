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



def build_checkout_log_entry(
    session_id: str,
    pushed_ids: list,
    cart_ids: list,
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

    return {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "emotions_summary": emotions_summary,
        "speech_summary": " / ".join(speeches) if speeches else "",
        "languages": languages,
        "pushed_ids": unique_pushed,
        "final_cart_ids": cart_ids,
        "is_success": is_success
    }
