"""Guardrails for RAG-backed promotion and policy answers."""


PROMOTION_KEYWORDS = {
    "優惠", "活動", "折扣", "特價", "促銷", "買一送一", "加購", "會員優惠",
    "coupon", "discount", "promotion", "deal", "offer",
}

POLICY_KEYWORDS = {
    "退款", "退費", "付款", "發票", "營業", "供應時間", "過敏", "營養", "成分",
    "refund", "payment", "invoice", "allergen", "nutrition", "opening",
}

UNVERIFIED_PROMOTION_TERMS = {
    "優惠", "折扣", "特價", "促銷", "買一送一", "限時優惠", "加購價", "半價",
    "discount", "deal", "coupon", "promotion",
}


def _text_contains_any(text: str, keywords: set[str]) -> bool:
    normalized = str(text or "").lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _visible_offers(offers: list[dict], audience: str = "guest") -> list[dict]:
    rows = []
    for offer in offers or []:
        if not isinstance(offer, dict):
            continue
        if offer.get("member_only") and audience != "member":
            continue
        rows.append(offer)
    return rows


def _offer_targets_item(offer: dict, item_id: str, category: str = "") -> bool:
    item_ids = {str(value or "").strip() for value in offer.get("item_ids") or []}
    categories = {str(value or "").strip() for value in offer.get("categories") or []}
    return bool((item_id and item_id in item_ids) or (category and category in categories))


def is_promotion_query(text: str) -> bool:
    return _text_contains_any(text, PROMOTION_KEYWORDS)


def is_policy_query(text: str) -> bool:
    return _text_contains_any(text, POLICY_KEYWORDS)


def build_voice_guard_section(
    query: str,
    *,
    offers: list[dict] | None = None,
    audience: str = "guest",
    rag_context: str = "",
) -> str:
    promotion_query = is_promotion_query(query)
    policy_query = is_policy_query(query)
    if not promotion_query and not policy_query:
        return ""

    visible_offers = _visible_offers(offers or [], audience)
    lines = ["【RAG 回答防編造規則】"]
    if promotion_query:
        if visible_offers:
            lines.append("顧客詢問優惠或活動時，只能使用【已驗證 RAG 優惠】列出的活動名稱、條件與適用品項。")
            lines.append("未列出的折扣、價格、買一送一、加購價、期間或會員權益一律不得自行補充。")
        else:
            lines.append("顧客詢問優惠或活動，但目前沒有可對該受眾確認的已驗證活動。")
            lines.append("回答時請說目前沒有查到可確認的活動，並請顧客以現場公告或結帳畫面為準；不得編造折扣或活動。")
    if policy_query:
        if rag_context:
            lines.append("顧客詢問政策、營養、過敏原、付款或營業資訊時，只能依據 RAG 補充資訊與菜單白名單回答。")
        else:
            lines.append("顧客詢問政策、營養、過敏原、付款或營業資訊，但目前沒有 RAG 補充資訊；請保守回答並請顧客以現場公告為準。")
    return "\n".join(lines)


def build_ai_push_guard_section(
    *,
    item_id: str,
    category: str = "",
    offers: list[dict] | None = None,
    audience: str = "guest",
) -> str:
    visible_offers = [
        offer
        for offer in _visible_offers(offers or [], audience)
        if _offer_targets_item(offer, item_id, category)
    ]
    lines = ["【推播文案防編造規則】"]
    if visible_offers:
        titles = "、".join(str(offer.get("title") or offer.get("offer_id") or "").strip() for offer in visible_offers if offer)
        lines.append(f"此餐點可引用的已驗證活動：{titles or '無'}。")
        lines.append("push_text 若提到優惠，只能使用上述活動，不得新增折扣、價格或期限。")
    else:
        lines.append("此餐點目前沒有已驗證活動；push_text 不得出現優惠、折扣、特價、買一送一、限時優惠、加購價等促銷詞。")
    return "\n".join(lines)


def sanitize_unverified_promotion_claims(text: str, item_name: str, *, has_verified_offer: bool) -> str:
    clean_text = str(text or "").strip()
    if has_verified_offer or not clean_text:
        return clean_text
    if _text_contains_any(clean_text, UNVERIFIED_PROMOTION_TERMS):
        return f"{item_name}現在很適合來一份，搭配點餐剛剛好！"
    return clean_text
