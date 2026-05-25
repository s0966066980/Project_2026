import re

from services import recommendation_service


def _contains_any(text: str, terms: list[str]) -> bool:
    normalized = recommendation_service.normalize_order_text(text)
    return any(recommendation_service.normalize_order_text(term) in normalized for term in terms)


def route_query(user_text: str, menu_items: list[dict]) -> dict:
    normalized = recommendation_service.normalize_order_text(user_text)
    if not normalized:
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "reason": "empty_query",
            "requires_rag": False,
            "requires_llm": False,
        }

    direct_terms = [
        "我要", "幫我加", "幫我點", "來一個", "來一份", "來一杯",
        "點兩份", "點一份", "一杯", "一份", "一個", "加一份",
        "add", "order", "iwant", "caniget",
    ]
    if _contains_any(user_text, direct_terms):
        actions = recommendation_service.coerce_cart_actions([], user_text, menu_items)
        if actions:
            return {
                "intent": "direct_order",
                "confidence": 0.95,
                "reason": "direct_order_terms_and_menu_match",
                "requires_rag": False,
                "requires_llm": False,
            }

    runtime_terms = [
        "目前客服模式", "客服模式", "目前模型", "使用模型", "rag狀態",
        "rag status", "語音模型", "推薦間隔", "目前設定", "系統設定",
        "emotion功能", "情緒功能",
    ]
    if _contains_any(user_text, runtime_terms):
        return {
            "intent": "runtime_setting",
            "confidence": 0.9,
            "reason": "runtime_setting_terms",
            "requires_rag": False,
            "requires_llm": False,
        }

    rag_terms = [
        "政策", "活動", "操作規則", "客服話術", "優惠券規則", "優惠券",
        "折扣碼", "後台設定", "專利流程", "測試規格", "員工", "制度",
        "規範", "說明文件", "申請", "隱私", "保留", "刪除紀錄",
        "policy", "coupon", "rule", "patent", "spec", "admin",
    ]
    if _contains_any(user_text, rag_terms):
        return {
            "intent": "rag_question",
            "confidence": 0.84,
            "reason": "rag_document_terms",
            "requires_rag": True,
            "requires_llm": True,
        }

    recommend_terms = [
        "推薦給我", "幫我推薦", "幫我選", "幫我挑", "我不知道吃什麼",
        "不知道要吃什麼", "不知道吃啥", "吃什麼好", "要吃什麼", "推薦點什麼",
        "想吃看看", "有什麼好吃的", "今天吃什麼", "推什麼", "推一下",
        "recommend me", "what should i eat", "what do you recommend",
        "any recommendation", "surprise me", "pick for me",
    ]
    if _contains_any(user_text, recommend_terms):
        return {
            "intent": "ask_recommendation",
            "confidence": 0.92,
            "reason": "explicit_recommend_request",
            "requires_rag": False,
            "requires_llm": True,
        }

    menu_terms = [
        "推薦", "最快", "雞肉", "雞", "牛肉", "牛", "魚", "不辣",
        "便宜", "飲料", "早餐", "薯條", "咖啡", "可樂", "漢堡",
        "套餐", "單點", "菜單", "餐點", "吃什麼", "喝什麼",
        "recommend", "chicken", "beef", "fish", "fries", "coffee",
        "drink", "burger", "fast", "quick",
    ]
    if _contains_any(user_text, menu_terms):
        return {
            "intent": "menu_question",
            "confidence": 0.82,
            "reason": "menu_whitelist_terms",
            "requires_rag": False,
            "requires_llm": False,
        }

    if re.search(r"(怎麼辦|怎麼處理|如何|為什麼|是什麼|能不能)", str(user_text or "")):
        return {
            "intent": "general_question",
            "confidence": 0.55,
            "reason": "general_explanation_question",
            "requires_rag": True,
            "requires_llm": True,
        }

    return {
        "intent": "unknown",
        "confidence": 0.35,
        "reason": "no_rule_matched",
        "requires_rag": False,
        "requires_llm": False,
    }
