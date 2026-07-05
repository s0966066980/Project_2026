"""統一推薦引擎。

此層只處理推薦候選、加權、去重與 prompt section 格式化。
資料收集由 recommendation_context_service 負責，AI push / voice 只負責呈現。
"""
import random

import config


def _price(item: dict) -> int:
    try:
        return int(float(item.get("price") or 0))
    except Exception:
        return 0


def _item_id(item: dict) -> str:
    return str(item.get("id") or "").strip()


def _category(item: dict) -> str:
    return str(item.get("category") or "").strip()


def _valid_menu_items(menu_items: list[dict], exclude_ids: set[str]) -> list[dict]:
    rows = []
    for item in menu_items or []:
        item_id = _item_id(item)
        if not item_id or item_id in exclude_ids or _price(item) <= 0:
            continue
        rows.append(item)
    return rows


def _preference_categories(preferences: dict) -> set[str]:
    return {
        str(category or "").strip()
        for category in preferences.get("preferred_categories") or []
        if str(category or "").strip()
    }


def _cart_ids(context: dict) -> set[str]:
    return {
        str(cart_item_id or "").strip()
        for cart_item_id in context.get("cart", {}).get("item_ids") or []
        if str(cart_item_id or "").strip()
    }


def _pairs_with_cart(item_id: str, context: dict) -> bool:
    if not item_id:
        return False
    cart_ids = _cart_ids(context)
    if not cart_ids or item_id in cart_ids:
        return False
    for pair in context.get("preferences", {}).get("frequent_pairs") or []:
        pair_ids = {
            str(pair_item_id or "").strip()
            for pair_item_id in pair.get("item_ids") or []
            if str(pair_item_id or "").strip()
        }
        if item_id in pair_ids and cart_ids.intersection(pair_ids):
            return True
    return False


def _eligible_offers(context: dict) -> list[dict]:
    audience = context.get("audience", "guest")
    cart_ids = _cart_ids(context)
    rows = []
    for offer in context.get("rag", {}).get("offers") or []:
        if offer.get("member_only") and audience != "member":
            continue
        required_cart_ids = {
            str(item_id or "").strip()
            for item_id in offer.get("required_cart_item_ids") or []
            if str(item_id or "").strip()
        }
        if required_cart_ids and not cart_ids.intersection(required_cart_ids):
            continue
        rows.append(offer)
    return rows


def _matching_offers(item: dict, context: dict) -> list[dict]:
    item_id = _item_id(item)
    category = _category(item)
    matches = []
    for offer in _eligible_offers(context):
        item_ids = set(offer.get("item_ids") or [])
        categories = set(offer.get("categories") or [])
        if item_id in item_ids or (category and category in categories):
            matches.append(offer)
    return matches


def _offer_ids(offers: list[dict]) -> list[str]:
    rows = []
    seen = set()
    for offer in offers or []:
        offer_id = str(offer.get("offer_id") or "").strip()
        if offer_id and offer_id not in seen:
            seen.add(offer_id)
            rows.append(offer_id)
    return rows


def _feedback_penalty(item_id: str, offers: list[dict], context: dict) -> int:
    feedback = context.get("feedback") if isinstance(context.get("feedback"), dict) else {}
    penalty = int((feedback.get("penalty_by_item_id") or {}).get(item_id, 0) or 0)
    offer_penalties = feedback.get("penalty_by_offer_id") or {}
    for offer_id in _offer_ids(offers):
        penalty += int(offer_penalties.get(offer_id, 0) or 0)
    return max(0, penalty)


def _availability_penalty(item_id: str, context: dict) -> int:
    availability = context.get("availability") if isinstance(context.get("availability"), dict) else {}
    low_stock_ids = {
        str(value or "").strip()
        for value in availability.get("low_stock_item_ids") or []
        if str(value or "").strip()
    }
    if item_id not in low_stock_ids:
        return 0
    return max(0, int(availability.get("low_stock_penalty") or config.get("RECOMMENDATION_LOW_STOCK_PENALTY", 1) or 0))


def _candidate_reason(item_id: str, context: dict) -> list[str]:
    reasons = []
    preferences = context.get("preferences", {})
    global_context = context.get("global", {})
    priority_categories = set(global_context.get("priority_categories") or [])
    preference_categories = _preference_categories(preferences)
    menu_item = next(
        (item for item in context.get("menu_items", []) if _item_id(item) == item_id),
        {},
    )
    category = _category(menu_item)

    if item_id in set(preferences.get("usual_item_ids") or []):
        reasons.append("member_usual")
    if item_id in set(preferences.get("recent_item_ids") or []):
        reasons.append("member_recent")
    if category and category in preference_categories:
        reasons.append("member_category")
    if _pairs_with_cart(item_id, context):
        reasons.append("member_pairing")
    if item_id in set(global_context.get("popular_item_ids") or []):
        reasons.append("global_popular")
    if category in priority_categories:
        reasons.append("priority_category")
    for offer in _matching_offers(menu_item, context):
        item_ids = set(offer.get("item_ids") or [])
        categories = set(offer.get("categories") or [])
        if offer.get("member_only"):
            reasons.append("member_offer")
        if item_id in item_ids:
            reasons.append("rag_offer")
        elif category and category in categories:
            reasons.append("rag_category_offer")
    if _feedback_penalty(item_id, _matching_offers(menu_item, context), context) > 0:
        reasons.append("recently_ignored")
    if _availability_penalty(item_id, context) > 0:
        reasons.append("low_stock")
    deduped = []
    seen = set()
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            deduped.append(reason)
    return deduped or ["menu_available"]


def score_item(item: dict, context: dict) -> int:
    item_id = _item_id(item)
    preferences = context.get("preferences", {})
    global_context = context.get("global", {})
    priority_categories = set(global_context.get("priority_categories") or [])
    preference_categories = _preference_categories(preferences)
    category = _category(item)

    score = 1
    if item_id in set(global_context.get("popular_item_ids") or []):
        score = max(score, int(config.get("RECOMMENDATION_POPULAR_WEIGHT", 3)))
    if item_id in set(preferences.get("usual_item_ids") or []):
        score = max(score, int(config.get("MEMBER_PUSH_WEIGHT", 4)))
    if item_id in set(preferences.get("recent_item_ids") or []):
        score = max(score, int(config.get("RECOMMENDATION_RECENT_WEIGHT", 3)))
    if category and category in preference_categories:
        score = max(score, int(config.get("RECOMMENDATION_CATEGORY_WEIGHT", 3)))
    if _pairs_with_cart(item_id, context):
        score = max(score, int(config.get("RECOMMENDATION_PAIR_WEIGHT", 5)))
    if category in priority_categories:
        score = max(score, int(config.get("RECOMMENDATION_PRIORITY_CATEGORY_WEIGHT", 2)))
    offers = _matching_offers(item, context)
    for offer in offers:
        if item_id in set(offer.get("item_ids") or []):
            score = max(score, int(offer.get("score_boost") or config.get("RECOMMENDATION_RAG_OFFER_WEIGHT", 4)))
        elif category and category in set(offer.get("categories") or []):
            score = max(
                score,
                int(offer.get("category_score_boost") or config.get("RECOMMENDATION_RAG_CATEGORY_WEIGHT", 2)),
            )
    score -= _feedback_penalty(item_id, offers, context)
    score -= _availability_penalty(item_id, context)
    return max(1, score)


def build_candidates(context: dict) -> list[dict]:
    exclude_ids = set(context.get("controls", {}).get("exclude_item_ids") or [])
    candidates = []
    for item in _valid_menu_items(context.get("menu_items", []), exclude_ids):
        item_id = _item_id(item)
        score = score_item(item, context)
        offers = _matching_offers(item, context)
        feedback_penalty = _feedback_penalty(item_id, offers, context)
        availability_penalty = _availability_penalty(item_id, context)
        candidates.append({
            "id": item_id,
            "name": str(item.get("name") or ""),
            "category": str(item.get("category") or ""),
            "price": _price(item),
            "image": item.get("official_image_url") or item.get("image", ""),
            "score": score,
            "reasons": _candidate_reason(item_id, context),
            "offer_ids": _offer_ids(offers),
            "offers": offers,
            "feedback_penalty": feedback_penalty,
            "availability_penalty": availability_penalty,
            "source": "recommendation_engine",
        })
    return candidates


def weighted_pick(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    pool = []
    for candidate in candidates:
        pool.extend([candidate] * max(1, int(candidate.get("score") or 1)))
    return random.choice(pool)


def _ranked_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=lambda item: (-int(item.get("score") or 0), item.get("id", "")))


def _strategy_name(strategy: str | None, randomize: bool) -> str:
    normalized = str(strategy or "").strip()
    if normalized:
        return normalized
    return "weighted_random" if randomize else "ranked_top_score"


def recommend(
    context: dict,
    limit: int = 1,
    randomize: bool = True,
    strategy: str | None = None,
    experiment: dict | None = None,
) -> dict:
    candidates = build_candidates(context)
    selected = []
    used_ids: set[str] = set()
    resolved_strategy = _strategy_name(strategy, randomize)

    if resolved_strategy == "ranked_top_score":
        selected = _ranked_candidates(candidates)[:limit]
    elif randomize:
        available = list(candidates)
        while available and len(selected) < limit:
            picked = weighted_pick(available)
            if not picked:
                break
            selected.append(picked)
            used_ids.add(picked["id"])
            available = [candidate for candidate in available if candidate["id"] not in used_ids]
    else:
        selected = _ranked_candidates(candidates)[:limit]

    experiment_context = experiment if isinstance(experiment, dict) else context.get("experiment", {})

    return {
        "audience": context.get("audience", "guest"),
        "surface": context.get("controls", {}).get("surface", ""),
        "strategy": resolved_strategy,
        "experiment": experiment_context,
        "experiment_id": experiment_context.get("experiment_id", ""),
        "variant_id": experiment_context.get("variant_id", ""),
        "items": selected,
        "candidates": candidates,
        "context": context,
    }


def format_voice_recommendation_context(result: dict, limit: int = 3) -> str:
    items = (result.get("items") or [])[:limit]
    if not items:
        return ""
    lines = ["【推薦候選 TOP 3】"]
    for index, item in enumerate(items, start=1):
        reason = "、".join(item.get("reasons") or [])
        offers = "；".join(offer.get("title", "") for offer in item.get("offers") or [] if offer.get("title"))
        offer_text = f"｜優惠：{offers}" if offers else ""
        lines.append(f"{index}. {item['name']}（{item['id']}）｜{item.get('category', '')}｜{reason}{offer_text}")
    lines.append("回答推薦問題時，優先從上述候選與會員偏好中挑選；顧客未明確確認時不要直接加入購物車。")
    return "\n".join(lines)
