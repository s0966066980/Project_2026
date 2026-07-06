"""AI 推播服務 — 透過 Ollama 生成底部欄推播餐點與理由。"""
import asyncio
import re
import time

import ai_services
import config
from repositories import menu_repository
from services import (
    rag_guard_service,
    rag_offer_service,
    recommendation_context_service,
    recommendation_engine_service,
    recommendation_experiment_service,
)
from services.popular_service import get_top_items

_menu_cache: dict = {"items": None, "ts": 0.0}


async def _get_menu_cached() -> list:
    now = time.monotonic()
    ttl = float(config.get("VOICE_MENU_CACHE_TTL_SEC", 60.0))
    if _menu_cache["items"] is None or now - _menu_cache["ts"] > ttl:
        _menu_cache["items"] = await asyncio.to_thread(menu_repository.get_menu)
        _menu_cache["ts"] = now
    return _menu_cache["items"]


def _price(item: dict) -> int:
    try:
        return int(float(item.get("price") or 0))
    except Exception:
        return 0


def _weighted_pick(
    items: list[dict],
    exclude: set,
    top_weight: int = 3,
    member_ids=None,
    popular_ids=None,
) -> dict | None:
    """相容舊內部測試的 wrapper；實際推薦邏輯集中在 recommendation_engine_service。"""
    top_ids = list(popular_ids) if popular_ids is not None else [t["id"] for t in get_top_items(3) if t.get("id")]
    context = {
        "preferences": {
            "usual_item_ids": list(member_ids or []),
            "recent_item_ids": [],
        },
        "global": {
            "popular_item_ids": top_ids,
            "priority_categories": [],
        },
        "controls": {
            "exclude_item_ids": list(exclude or []),
            "surface": "ai_push",
        },
        "menu_items": items,
    }
    return recommendation_engine_service.weighted_pick(
        recommendation_engine_service.build_candidates(context)
    )


def _fallback_item(items: list[dict], exclude: set) -> dict:
    priority_cats = config.get("AI_PUSH_PRIORITY_CATS", [])
    candidates = [i for i in items if i.get("id") and i["id"] not in exclude and _price(i) > 0]
    for cat in priority_cats:
        hit = next((i for i in candidates if i.get("category") == cat), None)
        if hit:
            return hit
    return candidates[0] if candidates else (items[0] if items else {})


def _recommendation_metadata(item: dict, rank: int = 1, experiment: dict | None = None, strategy: str = "") -> dict:
    experiment_row = experiment if isinstance(experiment, dict) else {}
    return {
        "item_id": item.get("id", ""),
        "item_name": item.get("name", ""),
        "category": item.get("category", ""),
        "rank": rank,
        "score": item.get("score", 0),
        "reasons": item.get("reasons", []),
        "offer_ids": item.get("offer_ids", []),
        "offers": [
            {
                "offer_id": offer.get("offer_id", ""),
                "title": offer.get("title", ""),
                "member_only": bool(offer.get("member_only", False)),
                "item_ids": offer.get("item_ids") if isinstance(offer.get("item_ids"), list) else [],
                "categories": offer.get("categories") if isinstance(offer.get("categories"), list) else [],
                "pricing": offer.get("pricing") if isinstance(offer.get("pricing"), dict) else {},
                "ad": offer.get("ad") if isinstance(offer.get("ad"), dict) else {},
            }
            for offer in item.get("offers", [])
            if isinstance(offer, dict)
        ],
        "source": item.get("source", "recommendation_engine"),
        "strategy": strategy or experiment_row.get("strategy", ""),
        "experiment_id": experiment_row.get("experiment_id", ""),
        "variant_id": experiment_row.get("variant_id", ""),
    }


def _item_category(context: dict, item_id: str) -> str:
    for item in context.get("menu_items") or []:
        if isinstance(item, dict) and item.get("id") == item_id:
            return str(item.get("category") or "")
    return ""


def _has_verified_offer_for_item(context: dict, item_id: str, category: str = "") -> bool:
    audience = context.get("audience", "guest")
    for offer in context.get("rag", {}).get("offers") or []:
        if not isinstance(offer, dict):
            continue
        if offer.get("member_only") and audience != "member":
            continue
        item_ids = {str(value or "").strip() for value in offer.get("item_ids") or []}
        categories = {str(value or "").strip() for value in offer.get("categories") or []}
        if item_id in item_ids or (category and category in categories):
            return True
    return False


def _fallback_push_text(item_name: str, has_verified_offer: bool = False) -> str:
    if has_verified_offer:
        return f"{item_name}現在很適合來一份，搭配活動更有感！"
    return f"{item_name}現在很適合來一份，搭配點餐剛剛好！"


async def _generate_push_text(
    context: dict,
    item_id: str,
    item_name: str,
    ollama_semaphore,
    num_predict_override: int | None = None,
) -> tuple[str, str]:
    category = _item_category(context, item_id)
    has_verified_offer = _has_verified_offer_for_item(context, item_id, category)
    guard_section = rag_guard_service.build_ai_push_guard_section(
        item_id=item_id,
        category=category,
        offers=context.get("rag", {}).get("offers") or [],
        audience=context.get("audience", "guest"),
    )
    rag_section = ""
    if guard_section:
        rag_section = f"{guard_section}\n\n"
    if context.get("rag", {}).get("context"):
        rag_section += f"{context['rag']['context']}\n\n"
    offer_section = rag_offer_service.format_offer_prompt_section(
        context.get("rag", {}).get("offers") or [],
        audience=context.get("audience", "guest"),
        limit=3,
    )
    if offer_section:
        rag_section += f"{offer_section}\n\n"

    system = config.get("AI_PUSH_SYSTEM_PROMPT")
    member_section = ""
    ctx = recommendation_context_service.member_prompt_section(context)
    if ctx:
        member_section = f"{ctx}\n\n"
    user = (
        f"{rag_section}"
        f"{member_section}"
        f"【指定推播餐點】{item_id}｜{item_name}\n\n"
        f"push_text 必須是繁體中文，字數至少 {config.get('AI_PUSH_TEXT_MIN', 18)} 字、最多 {config.get('AI_PUSH_TEXT_MAX', 34)} 字，"
        f"自然熱情地促購此餐點，不要出現 JSON 以外的文字。"
        f'直接輸出：{{"recommendation_id":"{item_id}","push_text":"..."}}'
    )

    push_num_predict = num_predict_override if num_predict_override is not None else max(
        int(config.get("OLLAMA_NUM_PREDICT", 220)),
        int(config.get("AI_PUSH_TEXT_MAX", 34)) * 4
    )

    try:
        async with ollama_semaphore:
            raw = await asyncio.to_thread(
                ai_services.ask_ollama,
                system, user, "AI_PUSH",
                config.get("MODEL_NAME", "qwen3.5:4b"),
                push_num_predict,
            )
    except Exception as exc:
        raw = {"error": str(exc)}

    if isinstance(raw, list):
        raw = next((row for row in raw if isinstance(row, dict)), {})

    hard_cap = int(config.get("AI_PUSH_TEXT_MAX", 34)) * 2
    if not isinstance(raw, dict) or "error" in raw:
        return _fallback_push_text(item_name, has_verified_offer), "fallback"

    push_text = re.sub(r"\s+", " ", str(raw.get("push_text") or "")).strip()[:hard_cap]
    if not push_text:
        push_text = _fallback_push_text(item_name, has_verified_offer)
    push_text = rag_guard_service.sanitize_unverified_promotion_claims(
        push_text,
        item_name,
        has_verified_offer=has_verified_offer,
    )
    return push_text, "success"


async def generate(
    session_id: str,
    ollama_semaphore,
    exclude_ids: list[str] | None = None,
    num_predict_override: int | None = None,
    cart_ids: list[str] | None = None,
) -> dict:
    """
    呼叫 Ollama 選出 1 個推薦餐點並生成促購短句。
    回傳 {"recommendation_id": "MCDxxx", "push_text": "...", "status": "success|fallback"}
    """
    items   = await _get_menu_cached()
    by_id   = {i["id"]: i for i in items if i.get("id")}
    ids     = list(by_id)
    exclude = set(exclude_ids or [])
    fallback = _fallback_item(items, exclude)
    fb_id    = fallback.get("id") or (ids[0] if ids else "")
    fb_name  = fallback.get("name") or "推薦餐點"

    if not ids:
        return {"status": "error", "message": "menu is empty"}

    context = await recommendation_context_service.build_context(
        session_id,
        cart_ids=cart_ids,
        exclude_ids=list(exclude),
        rag_query="推薦 活動 特惠 主打 套餐",
        rag_top_k=2,
        surface="ai_push",
        menu_items=items,
    )
    experiment = recommendation_experiment_service.assign(session_id)
    context["experiment"] = experiment

    # 推薦品項由統一推薦引擎決定；此服務只負責 AI push 文案。
    recommendation = await asyncio.to_thread(
        recommendation_engine_service.recommend,
        context,
        1,
        True,
        experiment.get("strategy", ""),
        experiment,
    )
    picked = (recommendation.get("items") or [None])[0]
    if not picked:
        picked = fallback
    sel_id   = picked.get("id") or fb_id
    sel_name = picked.get("name") or fb_name

    push_text, status = await _generate_push_text(
        context,
        sel_id,
        sel_name,
        ollama_semaphore,
        num_predict_override,
    )

    return {
        "status": status,
        "session_id": session_id,
        "recommendation_id": sel_id,
        "push_text": push_text,
        "experiment": experiment,
        "strategy": recommendation.get("strategy", experiment.get("strategy", "")),
        "experiment_id": experiment.get("experiment_id", ""),
        "variant_id": experiment.get("variant_id", ""),
        "recommendation": _recommendation_metadata(
            picked,
            1,
            experiment,
            recommendation.get("strategy", experiment.get("strategy", "")),
        ),
    }


async def generate_three(session_id: str, ollama_semaphore, cart_ids: list[str] | None = None) -> list[dict]:
    """由統一推薦引擎一次選出三個不重複品項，再沿用單品推播文案格式。"""
    items = await _get_menu_cached()
    items_map = {i["id"]: i for i in items if i.get("id")}
    context = await recommendation_context_service.build_context(
        session_id,
        cart_ids=cart_ids,
        surface="assist_recommend",
        menu_items=items,
    )
    experiment = recommendation_experiment_service.assign(session_id)
    context["experiment"] = experiment
    recommendation = await asyncio.to_thread(
        recommendation_engine_service.recommend,
        context,
        3,
        True,
        experiment.get("strategy", ""),
        experiment,
    )

    results = []
    for index, item in enumerate(recommendation.get("items", []), start=1):
        rec_id = item.get("id", "")
        menu_item = items_map.get(rec_id, {})
        item_name = menu_item.get("name", "") or item.get("name", "") or "推薦餐點"
        push_text, _ = await _generate_push_text(
            context,
            rec_id,
            item_name,
            ollama_semaphore,
            80,
        )
        results.append({
            "id": rec_id,
            "name": item_name,
            "price": menu_item.get("price", 0),
            "image": menu_item.get("official_image_url") or menu_item.get("image", ""),
            "push_text": push_text,
            "category": menu_item.get("category", ""),
            "rank": index,
            "score": item.get("score", 0),
            "reasons": item.get("reasons", []),
            "offer_ids": item.get("offer_ids", []),
            "strategy": recommendation.get("strategy", experiment.get("strategy", "")),
            "experiment_id": experiment.get("experiment_id", ""),
            "variant_id": experiment.get("variant_id", ""),
            "offers": [
                {
                    "offer_id": offer.get("offer_id", ""),
                    "title": offer.get("title", ""),
                    "member_only": bool(offer.get("member_only", False)),
                    "item_ids": offer.get("item_ids") if isinstance(offer.get("item_ids"), list) else [],
                    "categories": offer.get("categories") if isinstance(offer.get("categories"), list) else [],
                    "pricing": offer.get("pricing") if isinstance(offer.get("pricing"), dict) else {},
                    "ad": offer.get("ad") if isinstance(offer.get("ad"), dict) else {},
                }
                for offer in item.get("offers", [])
                if isinstance(offer, dict)
            ],
            "source": item.get("source", "recommendation_engine"),
        })
    return results
