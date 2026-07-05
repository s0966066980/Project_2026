"""推薦事件服務。

負責正規化推薦生命週期事件，並在結帳時補上成交/忽略事件。
"""
from collections import Counter, defaultdict
from datetime import datetime
import time

from repositories import recommendation_event_repository
from services import member_service


EVENT_TYPES = {
    "recommendation_generated",
    "recommendation_shown",
    "recommendation_clicked",
    "recommendation_added_to_cart",
    "recommendation_removed_from_cart",
    "recommendation_checked_out",
    "recommendation_ignored",
}

RECOMMENDATION_CART_SOURCES = {
    "ai_push": "ai_push",
    "assist_recommend": "assist_recommend",
    "voice_assist": "voice",
    "voice": "voice",
    "choice_hesitation": "choice_hesitation",
    "member_usual": "member_usual",
    "global_popular": "global_popular",
}

SAFE_METADATA_KEYS = {
    "cart_source",
    "offer_id",
    "offer_ids",
    "offer_titles",
    "experiment_id",
    "variant_id",
    "reason",
    "source",
    "strategy",
    "model_status",
    "push_text",
    "rank",
}

SAFE_UI_CONTEXT_KEYS = {
    "page_id",
    "cart_count",
    "cart_total",
    "voice_assist_enabled",
    "recommend_enabled",
    "recommendation_surface",
    "recommendation_source",
}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


def _safe_text(value, limit: int = 160) -> str:
    return str(value or "").strip()[:limit]


def _as_int(value, default: int = 0, upper: int = 999) -> int:
    try:
        return max(0, min(upper, int(float(value))))
    except Exception:
        return default


def _as_float(value, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except Exception:
        return default


def _safe_reasons(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_safe_text(reason, 80) for reason in value if _safe_text(reason, 80)][:8]


def _safe_text_list(value, *, limit: int = 12, text_limit: int = 100) -> list[str]:
    if isinstance(value, str):
        raw_rows = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        raw_rows = value
    else:
        return []
    rows = []
    seen = set()
    for raw in raw_rows:
        text = _safe_text(raw, text_limit)
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
        if len(rows) >= limit:
            break
    return rows


def _safe_metadata(value) -> dict:
    if not isinstance(value, dict):
        return {}
    safe = {}
    for key in SAFE_METADATA_KEYS:
        if key not in value:
            continue
        raw = value.get(key)
        if key in {"offer_ids", "offer_titles"}:
            safe[key] = _safe_text_list(raw)
        elif isinstance(raw, (str, int, float, bool)):
            safe[key] = raw if not isinstance(raw, str) else raw[:160]
    if safe.get("offer_id") and not safe.get("offer_ids"):
        safe["offer_ids"] = [_safe_text(safe["offer_id"], 100)]
    return safe


def _offer_metadata(raw: dict) -> dict:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    offer_ids = _safe_text_list(raw.get("offer_ids") or metadata.get("offer_ids") or metadata.get("offer_id"))
    offer_titles = _safe_text_list(raw.get("offer_titles") or metadata.get("offer_titles"))
    rows = {}
    if offer_ids:
        rows["offer_ids"] = offer_ids
        rows["offer_id"] = offer_ids[0]
    if offer_titles:
        rows["offer_titles"] = offer_titles
    return rows


def _experiment_metadata(raw: dict) -> dict:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    experiment_id = _safe_text(raw.get("experiment_id") or metadata.get("experiment_id"), 100)
    variant_id = _safe_text(raw.get("variant_id") or metadata.get("variant_id"), 100)
    strategy = _safe_text(raw.get("strategy") or metadata.get("strategy"), 100)
    rows = {}
    if experiment_id:
        rows["experiment_id"] = experiment_id
    if variant_id:
        rows["variant_id"] = variant_id
    if strategy:
        rows["strategy"] = strategy
    return rows


def _safe_ui_context(value) -> dict:
    if not isinstance(value, dict):
        return {}
    safe = {}
    for key in SAFE_UI_CONTEXT_KEYS:
        if key not in value:
            continue
        raw = value.get(key)
        if isinstance(raw, (str, int, float, bool)):
            safe[key] = raw if not isinstance(raw, str) else raw[:120]
    return safe


def _member_snapshot(session_id: str) -> dict:
    member = member_service.get_session_member(session_id)
    if not member:
        return {
            "is_member": False,
            "member_phone_masked": "",
            "member_nickname": "",
        }
    return {
        "is_member": True,
        "member_phone_masked": member_service.mask_phone(member.get("phone", "")),
        "member_nickname": _safe_text(member.get("nickname", ""), 80),
    }


def _surface_from_source(source: str, fallback: str = "") -> str:
    normalized = _safe_text(source, 80)
    return RECOMMENDATION_CART_SOURCES.get(normalized, fallback or normalized or "unknown")


def normalize_recommendation_event(payload: dict) -> dict:
    raw = payload if isinstance(payload, dict) else {}
    session_id = _safe_text(raw.get("session_id") or "anonymous", 100)
    event_type = _safe_text(raw.get("event_type") or "recommendation_shown", 80)
    if event_type not in EVENT_TYPES:
        event_type = "recommendation_shown"
    item_id = _safe_text(raw.get("item_id") or raw.get("recommended_item_id"), 80)
    surface = _safe_text(raw.get("surface") or "unknown", 80)
    source = _safe_text(raw.get("source") or surface or "unknown", 80)
    now_ms = _timestamp_ms()
    recommendation_id = _safe_text(raw.get("recommendation_id"), 140)
    if not recommendation_id:
        recommendation_id = f"rec_{session_id}_{surface}_{item_id or 'unknown'}_{now_ms}"

    record = {
        "event_id": _safe_text(raw.get("event_id"), 140) or f"rev_{session_id}_{now_ms}",
        "recommendation_id": recommendation_id,
        "session_id": session_id,
        "event_type": event_type,
        "surface": surface,
        "source": source,
        "item_id": item_id,
        "item_name": _safe_text(raw.get("item_name"), 120),
        "category": _safe_text(raw.get("category"), 80),
        "rank": _as_int(raw.get("rank"), 0, 100),
        "score": _as_float(raw.get("score"), 0.0),
        "reasons": _safe_reasons(raw.get("reasons")),
        "quantity": _as_int(raw.get("quantity"), 0, 100),
        "audience": _safe_text(raw.get("audience") or "guest", 40),
        "metadata": {
            **_safe_metadata(raw.get("metadata")),
            **_offer_metadata(raw),
            **_experiment_metadata(raw),
        },
        "ui_context": _safe_ui_context(raw.get("ui_context")),
        "timestamp": _safe_text(raw.get("timestamp"), 40) or _now_iso(),
    }
    record.update(_member_snapshot(session_id))
    if record["is_member"]:
        record["audience"] = "member"
    return record


def record_recommendation_event(payload: dict) -> dict:
    event = normalize_recommendation_event(payload)
    return recommendation_event_repository.append_recommendation_event(event)


def _cart_quantities(cart_ids: list, cart_items: list | None = None) -> dict[str, int]:
    quantities: dict[str, int] = {}
    if isinstance(cart_items, list) and cart_items:
        for item in cart_items:
            if not isinstance(item, dict):
                continue
            item_id = _safe_text(item.get("id"), 80)
            if not item_id:
                continue
            quantities[item_id] = quantities.get(item_id, 0) + _as_int(item.get("quantity", item.get("qty", 1)), 1, 100)
    if quantities:
        return dict(quantities)
    for item_id in cart_ids or []:
        normalized = _safe_text(item_id, 80)
        if normalized:
            quantities[normalized] = quantities.get(normalized, 0) + 1
    return dict(quantities)


def _sources_by_item(cart_sources: list | None) -> dict[str, str]:
    sources = {}
    for row in cart_sources or []:
        if not isinstance(row, dict):
            continue
        item_id = _safe_text(row.get("id"), 80)
        source = _safe_text(row.get("source"), 80)
        if item_id and source:
            sources[item_id] = source
    return sources


def _latest_recommendation_by_item(events: list) -> dict[str, dict]:
    latest = {}
    for event in events:
        item_id = _safe_text(event.get("item_id"), 80)
        if not item_id:
            continue
        if event.get("event_type") in {
            "recommendation_generated",
            "recommendation_shown",
            "recommendation_clicked",
            "recommendation_added_to_cart",
        }:
            latest[item_id] = event
    return latest


def record_checkout_recommendation_events(
    session_id: str,
    cart_ids: list,
    cart_items: list | None,
    cart_sources: list | None,
    pushed_ids: list | None,
) -> list[dict]:
    existing = recommendation_event_repository.get_recommendation_events(session_id, 5000)
    latest_by_item = _latest_recommendation_by_item(existing)
    final_quantities = _cart_quantities(cart_ids, cart_items)
    final_ids = set(final_quantities)
    sources = _sources_by_item(cart_sources)
    pushed_set = {_safe_text(item_id, 80) for item_id in pushed_ids or [] if _safe_text(item_id, 80)}

    new_events = []
    for item_id, quantity in final_quantities.items():
        source = sources.get(item_id, "")
        base = latest_by_item.get(item_id, {})
        if not base and item_id not in pushed_set and source not in RECOMMENDATION_CART_SOURCES:
            continue
        surface = _surface_from_source(source, _safe_text(base.get("surface") or "checkout", 80))
        new_events.append(normalize_recommendation_event({
            "session_id": session_id,
            "event_type": "recommendation_checked_out",
            "recommendation_id": base.get("recommendation_id", ""),
            "surface": surface,
            "source": source or base.get("source") or surface,
            "item_id": item_id,
            "item_name": base.get("item_name", ""),
            "category": base.get("category", ""),
            "rank": base.get("rank", 0),
            "score": base.get("score", 0),
            "reasons": base.get("reasons", []),
            "quantity": quantity,
            "metadata": {
                "cart_source": source or base.get("source", ""),
                **_offer_metadata(base),
                **_experiment_metadata(base),
            },
        }))

    ignored_keys = {
        (event.get("recommendation_id"), event.get("item_id"))
        for event in existing
        if event.get("event_type") in {"recommendation_ignored", "recommendation_checked_out"}
    }
    for event in existing:
        if event.get("event_type") != "recommendation_shown":
            continue
        item_id = _safe_text(event.get("item_id"), 80)
        key = (event.get("recommendation_id"), item_id)
        if not item_id or item_id in final_ids or key in ignored_keys:
            continue
        new_events.append(normalize_recommendation_event({
            "session_id": session_id,
            "event_type": "recommendation_ignored",
            "recommendation_id": event.get("recommendation_id", ""),
            "surface": event.get("surface", ""),
            "source": event.get("source", ""),
            "item_id": item_id,
            "item_name": event.get("item_name", ""),
            "category": event.get("category", ""),
            "rank": event.get("rank", 0),
            "score": event.get("score", 0),
            "reasons": event.get("reasons", []),
            "metadata": {
                "reason": "checkout_without_item",
                **_offer_metadata(event),
                **_experiment_metadata(event),
            },
        }))

    return recommendation_event_repository.append_recommendation_events(new_events)


def build_recommendation_event_stats(events: list) -> dict:
    type_counts = Counter(event.get("event_type", "unknown") for event in events if isinstance(event, dict))
    surface_counts = defaultdict(Counter)
    source_counts = defaultdict(Counter)
    offer_counts = defaultdict(Counter)
    experiment_counts = defaultdict(Counter)
    variant_counts = defaultdict(Counter)
    strategy_counts = defaultdict(Counter)
    reason_counts = Counter()
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type", "unknown")
        surface_counts[event.get("surface", "unknown")][event_type] += 1
        source_counts[event.get("source", "unknown")][event_type] += 1
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        for offer_id in _safe_text_list(metadata.get("offer_ids") or metadata.get("offer_id")):
            offer_counts[offer_id][event_type] += 1
        experiment_id = _safe_text(metadata.get("experiment_id"), 100)
        variant_id = _safe_text(metadata.get("variant_id"), 100)
        strategy = _safe_text(metadata.get("strategy"), 100)
        if experiment_id:
            experiment_counts[experiment_id][event_type] += 1
        if variant_id:
            variant_key = f"{experiment_id}:{variant_id}" if experiment_id else variant_id
            variant_counts[variant_key][event_type] += 1
        if strategy:
            strategy_counts[strategy][event_type] += 1
        for reason in event.get("reasons") or []:
            reason_counts[reason] += 1

    shown = type_counts.get("recommendation_shown", 0)
    clicked = type_counts.get("recommendation_clicked", 0)
    added = type_counts.get("recommendation_added_to_cart", 0)
    checked_out = type_counts.get("recommendation_checked_out", 0)
    return {
        "total_events": len(events),
        "event_type_counts": dict(type_counts),
        "surface_counts": {key: dict(value) for key, value in surface_counts.items()},
        "source_counts": {key: dict(value) for key, value in source_counts.items()},
        "offer_counts": {key: dict(value) for key, value in offer_counts.items()},
        "experiment_counts": {key: dict(value) for key, value in experiment_counts.items()},
        "variant_counts": {key: dict(value) for key, value in variant_counts.items()},
        "strategy_counts": {key: dict(value) for key, value in strategy_counts.items()},
        "reason_counts": dict(reason_counts),
        "click_rate": round(clicked / shown, 4) if shown else 0,
        "add_rate": round(added / shown, 4) if shown else 0,
        "checkout_rate": round(checked_out / shown, 4) if shown else 0,
    }
