"""Resolve the push sentence for a menu item from pre-authored copy — never from an LLM.

Kiosk-facing push copy is authored in Admin ahead of time. At request time this module only
looks copy up, so a push can neither be slow, fail, nor invent a promotion. Campaign copy is
served only while the offer it names is still active, which is what stops authored promotional
wording from outliving the campaign behind it.
"""

from datetime import date

import config
from repositories import push_copy_repository

# Serving statuses recorded on recommendation telemetry. These replace the old runtime-generation
# statuses (success / guard_rewritten / fallback), which no longer describe anything real.
STATUS_CAMPAIGN = "authored_campaign"
STATUS_BASE = "authored_base"
STATUS_DESCRIPTION = "description_fallback"

SCOPE_MODES = ("all", "categories", "new_items", "popular")


def _text(value) -> str:
    return str(value or "").strip()


def active_offer_ids(offers: list[dict] | None, audience: str = "guest") -> set[str]:
    """Offer ids currently visible to this audience, from the already-loaded active offers."""

    ids = set()
    for offer in offers or []:
        if not isinstance(offer, dict):
            continue
        if offer.get("member_only") and audience != "member":
            continue
        offer_id = _text(offer.get("offer_id"))
        if offer_id:
            ids.add(offer_id)
    return ids


def resolve_copy(
    item: dict,
    entry: dict | None,
    *,
    live_offer_ids: set[str] | None = None,
) -> tuple[str, str]:
    """Return (push_text, status) for one item. Falls through campaign → base → description."""

    row = entry if isinstance(entry, dict) else {}
    campaign_copy = _text(row.get("campaign_copy"))
    campaign_offer_id = _text(row.get("campaign_offer_id"))
    if campaign_copy and campaign_offer_id and campaign_offer_id in (live_offer_ids or set()):
        return campaign_copy, STATUS_CAMPAIGN

    base_copy = _text(row.get("base_copy"))
    if base_copy:
        return base_copy, STATUS_BASE

    # No authored copy yet (freshly imported item, or nobody has written it). The menu's own
    # description is descriptive rather than promotional, but it is true, on-brand, and beats
    # showing the customer nothing.
    return _text(item.get("description")), STATUS_DESCRIPTION


def scope_mode() -> str:
    mode = _text(config.get("AI_PUSH_SCOPE_MODE", "all")).lower()
    return mode if mode in SCOPE_MODES else "all"


def eligible_item_ids(
    menu_items: list[dict],
    copy_rows: dict,
    *,
    popular_ids: list[str] | None = None,
    today: date | None = None,
) -> list[str]:
    """Item ids the configured push scope admits.

    This is a filter, not a ranking: whichever ids survive are handed to the recommendation
    engine, which still applies availability, ignore-feedback and offer weighting on top.
    """

    mode = scope_mode()
    rows = [item for item in menu_items or [] if isinstance(item, dict) and _text(item.get("id"))]

    if mode == "categories":
        wanted = {_text(name) for name in config.get("AI_PUSH_SCOPE_CATEGORIES", []) or []}
        wanted.discard("")
        # An empty category list would otherwise silently mean "push nothing at all".
        if wanted:
            rows = [item for item in rows if _text(item.get("category")) in wanted]
    elif mode == "new_items":
        rows = [
            item
            for item in rows
            if push_copy_repository.is_currently_new(copy_rows.get(_text(item.get("id")), {}), today)
        ]
    elif mode == "popular":
        ranked = [_text(value) for value in popular_ids or []]
        order = {item_id: index for index, item_id in enumerate(ranked)}
        rows = [item for item in rows if _text(item.get("id")) in order]
        rows.sort(key=lambda item: order.get(_text(item.get("id")), len(order)))

    return [_text(item.get("id")) for item in rows]
