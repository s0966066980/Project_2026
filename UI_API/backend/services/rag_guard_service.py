"""Guardrails for RAG-backed promotion and policy answers."""

PROMOTION_KEYWORDS = {
    "優惠",
    "活動",
    "折扣",
    "特價",
    "促銷",
    "買一送一",
    "加購",
    "會員優惠",
    "coupon",
    "discount",
    "promotion",
    "deal",
    "offer",
}

POLICY_KEYWORDS = {
    "退款",
    "退費",
    "付款",
    "發票",
    "營業",
    "供應時間",
    "過敏",
    "營養",
    "成分",
    "refund",
    "payment",
    "invoice",
    "allergen",
    "nutrition",
    "opening",
}

UNVERIFIED_PROMOTION_TERMS = {
    "優惠",
    "折扣",
    "特價",
    "促銷",
    "買一送一",
    "限時優惠",
    "加購價",
    "半價",
    "discount",
    "deal",
    "coupon",
    "promotion",
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
            lines.append(
                "顧客詢問政策、營養、過敏原、付款或營業資訊，但目前沒有 RAG 補充資訊；請保守回答並請顧客以現場公告為準。"
            )
    return "\n".join(lines)


def offers_targeting_item(
    item_id: str,
    *,
    category: str = "",
    offers: list[dict] | None = None,
    audience: str = "guest",
) -> list[dict]:
    """Offers visible to this audience that actually apply to this item."""

    return [offer for offer in _visible_offers(offers or [], audience) if _offer_targets_item(offer, item_id, category)]


def unverified_promotion_terms(text: str) -> list[str]:
    """Promotional terms present in authored push copy, for save-time rejection.

    Push copy is now written in Admin rather than generated per request, so a promotional claim
    would be shown to every customer until someone noticed — and campaigns end while static text
    does not. Base copy is therefore rejected at save time instead of rewritten at serve time.
    """

    normalized = str(text or "").lower()
    return sorted(term for term in UNVERIFIED_PROMOTION_TERMS if term.lower() in normalized)
