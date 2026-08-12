"""共用推薦上下文組裝。

第一階段只集中資料來源，不重寫推薦演算法。
"""

import asyncio

import config
from capabilities import catalog
from models.commercial_scope import CommercialScope
from services import (
    availability_service,
    member_preference_service,
    member_service,
    rag_offer_service,
    recommendation_feedback_service,
)
from services.popular_service import get_top_items


def _normalize_ids(values: list[str] | None) -> list[str]:
    seen = set()
    rows = []
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append(normalized)
    return rows


async def _rag_context(
    query: str,
    top_k: int | None = None,
    scope: CommercialScope | None = None,
) -> str:
    if not config.get("RAG_ENABLED", False):
        return ""
    try:
        from services.rag_provider import get_rag

        return await get_rag().query(query, top_k=top_k, scope=scope)
    except Exception:
        return ""


async def _rag_offers(
    menu_items: list[dict],
    scope: CommercialScope | None = None,
) -> list[dict]:
    try:
        if scope:
            return await asyncio.to_thread(
                rag_offer_service.load_active_offers,
                menu_items,
                scope=scope,
            )
        return await asyncio.to_thread(rag_offer_service.load_active_offers, menu_items)
    except Exception:
        return []


async def build_context(
    session_id: str,
    *,
    cart_ids: list[str] | None = None,
    exclude_ids: list[str] | None = None,
    rag_query: str = "",
    rag_top_k: int | None = None,
    surface: str = "",
    menu_items: list[dict] | None = None,
    scope: CommercialScope | None = None,
) -> dict:
    menu_rows = (
        menu_items
        if menu_items is not None
        else await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)
        if scope is not None
        else await asyncio.to_thread(catalog.list_active_items)
    )
    member = await asyncio.to_thread(
        member_service.get_session_member,
        session_id,
        *(() if scope is None else (scope,)),
    )
    preferences = await asyncio.to_thread(member_preference_service.build_preference_summary, member)
    popular_items = await asyncio.to_thread(get_top_items, 3)
    feedback_kwargs: dict[str, object] = {"member_phone_masked": preferences.get("phone_masked", "")}
    if scope:
        feedback_kwargs["scope"] = scope
    feedback = await asyncio.to_thread(
        recommendation_feedback_service.build_feedback_context,
        session_id,
        **feedback_kwargs,
    )
    availability = (
        await asyncio.to_thread(availability_service.build_availability_context, menu_rows, None, scope)
        if scope
        else await asyncio.to_thread(availability_service.build_availability_context, menu_rows)
    )
    rag, offers = await asyncio.gather(
        _rag_context(rag_query, top_k=rag_top_k, scope=scope) if rag_query else asyncio.sleep(0, result=""),
        _rag_offers(menu_rows, scope),
    )
    excluded_ids = [
        *(exclude_ids or []),
        *feedback.get("exclude_item_ids", []),
        *availability.get("exclude_item_ids", []),
    ]

    return {
        "session_id": session_id,
        "audience": "member" if preferences.get("has_member") else "guest",
        "member": {
            "has_member": bool(preferences.get("has_member")),
            "phone_masked": preferences.get("phone_masked", ""),
            "nickname": preferences.get("nickname", ""),
            "visit_count": int(preferences.get("visit_count", 0) or 0),
            "avg_spend": int(preferences.get("avg_spend", 0) or 0),
        },
        "preferences": preferences,
        "global": {
            "popular_item_ids": [str(item.get("id")) for item in popular_items if item.get("id")],
            "popular_items": popular_items,
            "priority_categories": list(config.get("AI_PUSH_PRIORITY_CATS", [])),
        },
        "cart": {
            "item_ids": _normalize_ids(cart_ids),
        },
        "controls": {
            "exclude_item_ids": _normalize_ids(excluded_ids),
            "surface": surface,
        },
        "feedback": feedback,
        "availability": availability,
        "rag": {
            "context": rag,
            "offers": offers,
        },
        "menu_items": menu_rows,
    }


def member_prompt_section(context: dict) -> str:
    return member_preference_service.format_member_prompt_section(context.get("preferences"))
