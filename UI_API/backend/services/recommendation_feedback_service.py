"""Short-term recommendation feedback derived from recommendation events."""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime

import config
from models.commercial_scope import CommercialScope
from repositories import recommendation_event_repository

NEGATIVE_EVENTS = {"recommendation_ignored"}
POSITIVE_EVENTS = {
    "recommendation_clicked",
    "recommendation_added_to_cart",
    "recommendation_checked_out",
}


def _safe_text(value, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _safe_text_list(value) -> list[str]:
    if isinstance(value, str):
        raw_rows = value.split(",")
    elif isinstance(value, list):
        raw_rows = value
    else:
        return []
    rows = []
    seen = set()
    for raw in raw_rows:
        text = _safe_text(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _event_timestamp(event: dict) -> float:
    raw = _safe_text(event.get("timestamp"), 60)
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _offer_ids(event: dict) -> list[str]:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    return _safe_text_list(metadata.get("offer_ids") or metadata.get("offer_id") or event.get("offer_ids"))


def _relevant(event: dict, session_id: str, member_phone_masked: str) -> bool:
    if _safe_text(event.get("session_id")) == session_id:
        return True
    if member_phone_masked and _safe_text(event.get("member_phone_masked")) == member_phone_masked:
        return True
    return False


def build_feedback_context(
    session_id: str,
    *,
    member_phone_masked: str = "",
    scope: CommercialScope | None = None,
) -> dict:
    if not config.get("RECOMMENDATION_IGNORE_FEEDBACK_ENABLED", True):
        return empty_feedback_context()

    session_id = _safe_text(session_id, 100)
    member_phone_masked = _safe_text(member_phone_masked, 80)
    window_seconds = int(config.get("RECOMMENDATION_IGNORE_WINDOW_MINUTES", 45) or 45) * 60
    limit = int(config.get("RECOMMENDATION_FEEDBACK_EVENT_LIMIT", 500) or 500)
    now = time.time()
    events = (
        recommendation_event_repository.get_recommendation_events_scoped(scope, "", limit)
        if scope
        else recommendation_event_repository.get_recommendation_events("", limit)
    )

    item_counts: Counter[str] = Counter()
    offer_counts: Counter[str] = Counter()
    relevant_events = [
        event
        for event in events
        if isinstance(event, dict)
        and _relevant(event, session_id, member_phone_masked)
        and event.get("event_type") in (NEGATIVE_EVENTS | POSITIVE_EVENTS)
        and (not window_seconds or (now - _event_timestamp(event)) <= window_seconds)
    ]

    for event in sorted(relevant_events, key=_event_timestamp):
        item_id = _safe_text(event.get("item_id"), 80)
        offer_ids = _offer_ids(event)
        event_type = event.get("event_type")
        if event_type in POSITIVE_EVENTS:
            if item_id:
                item_counts.pop(item_id, None)
            for offer_id in offer_ids:
                offer_counts.pop(offer_id, None)
            continue
        if event_type in NEGATIVE_EVENTS:
            if item_id:
                item_counts[item_id] += 1
            for offer_id in offer_ids:
                offer_counts[offer_id] += 1

    item_penalty = int(config.get("RECOMMENDATION_IGNORED_ITEM_PENALTY", 2) or 2)
    offer_penalty = int(config.get("RECOMMENDATION_IGNORED_OFFER_PENALTY", 1) or 1)
    exclude_threshold = int(config.get("RECOMMENDATION_IGNORED_ITEM_EXCLUDE_THRESHOLD", 3) or 3)
    return {
        "ignored_item_ids": sorted(item_counts),
        "ignored_offer_ids": sorted(offer_counts),
        "penalty_by_item_id": {item_id: count * item_penalty for item_id, count in item_counts.items()},
        "penalty_by_offer_id": {offer_id: count * offer_penalty for offer_id, count in offer_counts.items()},
        "exclude_item_ids": sorted(
            item_id for item_id, count in item_counts.items() if exclude_threshold > 0 and count >= exclude_threshold
        ),
        "window_minutes": window_seconds // 60 if window_seconds else 0,
    }


def empty_feedback_context() -> dict:
    return {
        "ignored_item_ids": [],
        "ignored_offer_ids": [],
        "penalty_by_item_id": {},
        "penalty_by_offer_id": {},
        "exclude_item_ids": [],
        "window_minutes": 0,
    }
