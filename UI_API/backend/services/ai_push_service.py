"""AI 推播服務 — 由推薦引擎選品，文案取自 Admin 預先撰寫的推薦詞。

執行時不呼叫 LLM：文案在 Admin 端撰寫並存於 menu_item_push_copy，此處只負責查表，
因此推播不會慢、不會失敗，也不可能編造促銷。詳見 docs/adr/0016。
"""
import asyncio
import logging
import time

from modules.recommendation import decide

import config
from models.commercial_scope import CommercialScope
from repositories import menu_repository, push_copy_repository
from services import (
    push_copy_service,
    recommendation_context_service,
    recommendation_engine_service,
    recommendation_experiment_service,
)
from services.popular_service import get_top_items

logger = logging.getLogger(__name__)

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


def _recommendation_metadata(
    item: dict,
    rank: int = 1,
    experiment: dict | None = None,
    strategy: str = "",
    model_status: str = "",
) -> dict:
    experiment_row = experiment if isinstance(experiment, dict) else {}
    return {
        # kiosk 遙測讀的是 recommendation.model_status；沒有它就永遠分不出
        # 文案是 LLM 生成、guard 改寫，還是 LLM 失敗備援。
        "model_status": model_status,
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


def _live_offer_ids(context: dict) -> set:
    """Offers active right now for this audience — the gate on serving campaign copy."""

    return push_copy_service.active_offer_ids(
        context.get("rag", {}).get("offers") or [],
        audience=context.get("audience", "guest"),
    )


def _push_text_for(
    item: dict,
    copy_rows: dict,
    live_offer_ids: set,
) -> tuple[str, str]:
    """Look up the authored sentence for one item. No LLM, no network, cannot fail."""

    item_id = str(item.get("id") or "")
    return push_copy_service.resolve_copy(
        item,
        copy_rows.get(item_id),
        live_offer_ids=live_offer_ids,
    )


async def _scope_controls(
    items: list[dict],
    copy_rows: dict,
    exclude: set,
) -> list[str]:
    """Ids the push scope excludes, merged with the caller's own exclusions.

    The scope is a filter over eligibility; ranking still belongs to the recommendation engine,
    so scope is expressed as exclusions rather than by handing it a pre-picked item.
    """

    popular_ids = [row.get("id") for row in await asyncio.to_thread(get_top_items, 20) if row.get("id")]
    eligible = set(push_copy_service.eligible_item_ids(items, copy_rows, popular_ids=popular_ids))
    excluded = {str(item.get("id")) for item in items if str(item.get("id") or "") not in eligible}
    return sorted(excluded | set(exclude))


async def generate(
    session_id: str,
    exclude_ids: list[str] | None = None,
    cart_ids: list[str] | None = None,
    scope: CommercialScope | None = None,
) -> dict:
    """選出 1 個推薦餐點，文案取自 Admin 預先撰寫的推薦詞（不呼叫 LLM）。

    回傳 {"recommendation_id": "MCDxxx", "push_text": "...", "status": "authored_base|..."}
    """
    items   = await _get_menu_cached()
    by_id   = {i["id"]: i for i in items if i.get("id")}
    ids     = list(by_id)
    exclude = set(exclude_ids or [])

    if not ids:
        return {"status": "error", "message": "menu is empty"}

    copy_rows = await asyncio.to_thread(
        push_copy_repository.list_copy_scoped, scope
    ) if scope else await asyncio.to_thread(push_copy_repository.list_copy)

    scoped_exclusions = await _scope_controls(items, copy_rows, exclude)
    fallback = _fallback_item(items, set(scoped_exclusions))
    fb_id    = fallback.get("id") or (ids[0] if ids else "")

    context = await recommendation_context_service.build_context(
        session_id,
        cart_ids=cart_ids,
        exclude_ids=scoped_exclusions,
        rag_query="推薦 活動 特惠 主打 套餐",
        rag_top_k=2,
        surface="ai_push",
        menu_items=items,
        scope=scope,
    )
    experiment = recommendation_experiment_service.assign(session_id)
    context["experiment"] = experiment

    # 推薦品項由統一推薦引擎決定；此服務只負責取出對應的預寫推薦詞。
    recommendation = await asyncio.to_thread(
        decide,
        context,
        session_id=session_id,
        scope=scope,
        limit=1,
        randomize=True,
        strategy=experiment.get("strategy", ""),
        experiment=experiment,
    )
    picked = (recommendation.get("items") or [None])[0]
    if not picked:
        picked = fallback
    sel_id   = picked.get("id") or fb_id

    push_text, status = _push_text_for(by_id.get(sel_id, picked), copy_rows, _live_offer_ids(context))

    return {
        "status": status,
        "session_id": session_id,
        "recommendation_id": sel_id,
        "push_text": push_text,
        "experiment": experiment,
        "strategy": recommendation.get("strategy", experiment.get("strategy", "")),
        "experiment_id": experiment.get("experiment_id", ""),
        "variant_id": experiment.get("variant_id", ""),
        "decision_id": recommendation.get("decision_id", ""),
        "strategy_version": recommendation.get("strategy_version", ""),
        "fallback_status": recommendation.get("fallback_status", ""),
        "recommendation": _recommendation_metadata(
            picked,
            1,
            experiment,
            recommendation.get("strategy", experiment.get("strategy", "")),
            model_status=status,
        ),
    }


async def generate_three(
    session_id: str,
    cart_ids: list[str] | None = None,
    scope: CommercialScope | None = None,
) -> list[dict]:
    """由統一推薦引擎一次選出三個不重複品項，文案同樣取自預寫推薦詞（不呼叫 LLM）。"""
    items = await _get_menu_cached()
    items_map = {i["id"]: i for i in items if i.get("id")}
    copy_rows = await asyncio.to_thread(
        push_copy_repository.list_copy_scoped, scope
    ) if scope else await asyncio.to_thread(push_copy_repository.list_copy)
    context = await recommendation_context_service.build_context(
        session_id,
        cart_ids=cart_ids,
        # Push Scope controls the passive push bar only.  The explicit assistance surface
        # should recommend any currently eligible menu item; cart and availability exclusions
        # are still applied by the shared recommendation context.
        exclude_ids=[],
        surface="assist_recommend",
        menu_items=items,
        scope=scope,
    )
    experiment = recommendation_experiment_service.assign(session_id)
    context["experiment"] = experiment
    recommendation = await asyncio.to_thread(
        decide,
        context,
        session_id=session_id,
        scope=scope,
        limit=3,
        randomize=True,
        strategy=experiment.get("strategy", ""),
        experiment=experiment,
    )

    live_offer_ids = _live_offer_ids(context)
    results = []
    for index, item in enumerate(recommendation.get("items", []), start=1):
        rec_id = item.get("id", "")
        menu_item = items_map.get(rec_id, {})
        item_name = menu_item.get("name", "") or item.get("name", "") or "推薦餐點"
        push_text, push_status = _push_text_for(menu_item or item, copy_rows, live_offer_ids)
        results.append({
            "model_status": push_status,
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
            "decision_id": recommendation.get("decision_id", ""),
            "strategy_version": recommendation.get("strategy_version", ""),
            "fallback_status": recommendation.get("fallback_status", ""),
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
