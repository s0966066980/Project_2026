"""Commercial touch ingestion with scope, privacy and idempotency rules."""

from __future__ import annotations

import json
from typing import Any

from modules.analytics.contracts import EffectivenessReport, TouchReceipt

from models.commercial_scope import CommercialScope
from services import analytics_pipeline_service

TOUCH_TYPES = {
    "decision",
    "impression",
    "click",
    "add_to_cart",
    "remove_from_cart",
    "purchase",
    "cancel",
    "ignore",
}
LEGACY_TYPE_MAP = {
    "recommendation_generated": "decision",
    "recommendation_shown": "impression",
    "recommendation_clicked": "click",
    "recommendation_added_to_cart": "add_to_cart",
    "recommendation_removed_from_cart": "remove_from_cart",
    "recommendation_checked_out": "purchase",
    "recommendation_ignored": "ignore",
}
SAFE_FIELDS = {
    "decision_id",
    "impression_id",
    "campaign_id",
    "campaign_version",
    "placement",
    "item_id",
    "rank",
    "strategy",
    "strategy_version",
    "experiment_id",
    "variant_id",
    "audience",
    "fallback_status",
    "order_id",
    "order_item_id",
    "quantity",
    "revenue",
    "discount",
    "metadata",
}


class TouchValidationError(ValueError):
    pass


def _text(value: Any, limit: int = 160) -> str:
    return str(value or "").strip()[:limit]


def _scope_matches(payload: dict, scope: CommercialScope) -> bool:
    tenant_id = _text(payload.get("tenant_id"), 40)
    store_id = _text(payload.get("store_id"), 40)
    device_id = _text(payload.get("device_id"), 40)
    return (
        (not tenant_id or tenant_id == str(scope.tenant_id))
        and (not store_id or store_id == str(scope.store_id))
        and (not device_id or scope.device_id is not None and device_id == str(scope.device_id))
    )


def record_touch(
    raw_payload: dict,
    scope: CommercialScope,
    *,
    sink: analytics_pipeline_service.AnalyticsSinkPort | None = None,
) -> TouchReceipt:
    payload = dict(raw_payload or {})
    event_id = _text(payload.get("event_id"), 140)
    if not event_id:
        raise TouchValidationError("event_id_required")
    if not _scope_matches(payload, scope):
        raise TouchValidationError("scope_mismatch")

    raw_type = _text(payload.get("event_type") or payload.get("type"), 80)
    event_type = LEGACY_TYPE_MAP.get(raw_type, raw_type)
    if event_type not in TOUCH_TYPES:
        raise TouchValidationError("unsupported_touch_type")
    normalized = {key: payload[key] for key in SAFE_FIELDS if key in payload}
    normalized["device_id"] = str(scope.device_id) if scope.device_id else ""
    decision_id = _text(normalized.get("decision_id"), 140)
    impression_id = _text(normalized.get("impression_id"), 140)
    data_quality = "complete"
    if event_type != "decision" and (not decision_id or (event_type != "impression" and not impression_id)):
        data_quality = "legacy_missing_touch_ids"
    normalized["decision_id"] = decision_id
    normalized["impression_id"] = impression_id
    normalized["data_quality"] = data_quality
    if len(json.dumps(normalized, ensure_ascii=False)) > 32_000:
        raise TouchValidationError("payload_too_large")
    try:
        analytics_pipeline_service.reject_forbidden_payload(normalized)
    except analytics_pipeline_service.AnalyticsError as exc:
        raise TouchValidationError(str(exc)) from exc

    if sink is None and analytics_pipeline_service.event_already_persisted(event_id):
        return TouchReceipt(event_id, False, True, data_quality)
    envelope = analytics_pipeline_service.build_envelope(
        event_type=f"commercial_touch.{event_type}",
        payload=normalized,
        tenant_id=scope.tenant_id,
        store_id=scope.store_id,
        session_ref=_text(payload.get("session_id"), 140),
        order_ref=_text(payload.get("order_id"), 140),
        source=_text(payload.get("source") or "kiosk", 80),
        schema_version="commercial-touch-v1",
        event_id=event_id,
        occurred_at=_text(payload.get("occurred_at") or payload.get("timestamp"), 60) or None,
    )
    accepted = analytics_pipeline_service.publish(envelope, sink=sink)
    return TouchReceipt(event_id, accepted, not accepted, data_quality)


def build_order_attributions(order: dict, touches: list[dict]) -> list[dict]:
    direct_types = {
        "add_to_cart",
        "recommendation_added_to_cart",
        "recommendation_checked_out",
    }
    view_types = {"impression", "recommendation_shown"}
    by_item: dict[str, dict[str, list[dict]]] = {}
    for touch in touches or []:
        item_id = _text(touch.get("item_id"), 100)
        event_type = _text(touch.get("event_type") or touch.get("type"), 80)
        if not item_id or event_type not in direct_types | view_types:
            continue
        bucket = by_item.setdefault(item_id, {"direct": [], "view_through": []})
        bucket["direct" if event_type in direct_types else "view_through"].append(touch)

    order_status = _text(order.get("status"), 40)
    attribution_status = (
        "reversed" if order_status == "cancelled"
        else ("confirmed" if order_status == "completed" else "provisional")
    )
    rows = []
    seen_items = set()
    for item in order.get("items") or []:
        order_item_id = item.get("order_item_id")
        item_id = _text(item.get("item_id") or item.get("id"), 100)
        if order_item_id in (None, "") or order_item_id in seen_items:
            continue
        candidates = by_item.get(item_id, {})
        attribution_type = "direct" if candidates.get("direct") else "view_through"
        matching = candidates.get(attribution_type) or []
        if not matching:
            continue
        touch = sorted(
            matching,
            key=lambda row: (_text(row.get("timestamp") or row.get("occurred_at"), 60), _text(row.get("event_id"), 140)),
        )[-1]
        seen_items.add(order_item_id)
        quantity = max(0, int(item.get("quantity") or 0))
        rows.append({
            "order_id": _text(order.get("order_id"), 140),
            "order_item_id": int(order_item_id),
            "item_id": item_id,
            "decision_id": _text(touch.get("decision_id") or touch.get("recommendation_id"), 140),
            "impression_id": _text(touch.get("impression_id"), 140),
            "attribution_type": attribution_type,
            "attributed_revenue": max(0, int(item.get("final_unit_price") or 0)) * quantity,
            "attributed_discount": max(0, int(item.get("discount_unit_total") or 0)) * quantity,
            "status": attribution_status,
        })
    return rows


def build_effectiveness_report(
    events: list[dict],
    attributions: list[dict],
    *,
    filters: dict[str, str] | None = None,
) -> EffectivenessReport:
    """Build a deduplicated recommendation/campaign funnel from durable facts."""

    active_filters = {str(key): str(value) for key, value in (filters or {}).items() if value not in (None, "")}
    touches: list[dict] = []
    for envelope in events or []:
        event_type = _text(envelope.get("type") or envelope.get("event_type"), 80)
        if event_type.startswith("commercial_touch."):
            event_type = event_type.split(".", 1)[1]
        payload = dict(envelope.get("payload") or {})
        payload["event_type"] = LEGACY_TYPE_MAP.get(event_type, event_type)
        payload["event_id"] = _text(envelope.get("event_id"), 140)
        payload["occurred_at"] = _text(envelope.get("occurred_at"), 60)
        if any(_text(payload.get(key), 160) != expected for key, expected in active_filters.items()):
            continue
        touches.append(payload)

    def keys(event_type: str) -> set[str]:
        return {
            _text(row.get("impression_id") or row.get("event_id"), 140)
            for row in touches
            if row.get("event_type") == event_type
        } - {""}

    impression_keys = keys("impression")
    click_keys = keys("click")
    add_keys = keys("add_to_cart")
    ignored_keys = keys("ignore") & impression_keys
    relevant_impressions = {
        _text(row.get("impression_id"), 140) for row in touches if row.get("impression_id")
    }
    scoped_attributions = [
        row for row in (attributions or [])
        if not active_filters or _text(row.get("impression_id"), 140) in relevant_impressions
    ]
    confirmed = [row for row in scoped_attributions if row.get("status") == "confirmed"]
    purchases = len({_text(row.get("order_item_id"), 140) for row in confirmed} - {""})
    impressions = len(impression_keys)
    incomplete = sum(1 for row in touches if row.get("data_quality") != "complete")

    breakdown_map: dict[str, dict[str, Any]] = {}
    for row in touches:
        variant = _text(row.get("variant_id") or "未設定分組", 100)
        bucket = breakdown_map.setdefault(variant, {"variant_id": variant, "impressions": set(), "clicks": set(), "add_to_carts": set()})
        event_type = row.get("event_type")
        if event_type in {"impression", "click", "add_to_cart"}:
            bucket[f"{event_type}s" if event_type != "add_to_cart" else "add_to_carts"].add(
                _text(row.get("impression_id") or row.get("event_id"), 140)
            )
    breakdowns = [
        {
            "variant_id": key,
            "impressions": len(value["impressions"]),
            "clicks": len(value["clicks"]),
            "add_to_carts": len(value["add_to_carts"]),
        }
        for key, value in sorted(breakdown_map.items())
    ]
    impression_variant = {
        _text(row.get("impression_id"), 140): _text(row.get("variant_id") or "未設定分組", 100)
        for row in touches
        if row.get("impression_id")
    }
    variant_purchases: dict[str, set[str]] = {}
    variant_revenue: dict[str, int] = {}
    for row in confirmed:
        variant = impression_variant.get(_text(row.get("impression_id"), 140), "未設定分組")
        variant_purchases.setdefault(variant, set()).add(_text(row.get("order_item_id"), 140))
        variant_revenue[variant] = variant_revenue.get(variant, 0) + max(0, int(row.get("attributed_revenue") or 0))
    comparison_rows = []
    if breakdowns:
        control = next((row for row in breakdowns if row["variant_id"].lower() in {"control", "控制組"}), breakdowns[0])
        control_impressions = int(control["impressions"])
        control_purchases = len(variant_purchases.get(control["variant_id"], set()))
        control_rate = control_purchases / control_impressions if control_impressions else 0.0
        for row in breakdowns:
            if row is control:
                continue
            variant_purchases_count = len(variant_purchases.get(row["variant_id"], set()))
            variant_rate = variant_purchases_count / row["impressions"] if row["impressions"] else 0.0
            difference = variant_rate - control_rate
            comparison_rows.append({
                "control_variant": control["variant_id"],
                "variant_id": row["variant_id"],
                "control_sample": control_impressions,
                "variant_sample": row["impressions"],
                "control_purchase_rate": round(control_rate, 4),
                "variant_purchase_rate": round(variant_rate, 4),
                "purchase_rate_difference": round(difference, 4),
                "relative_lift": round(difference / control_rate, 4) if control_rate else None,
                "attributed_revenue_per_purchase": round(
                    variant_revenue.get(row["variant_id"], 0) / variant_purchases_count, 2
                ) if variant_purchases_count else 0,
                "conclusion": "樣本不足，僅顯示觀察差異" if min(control_impressions, row["impressions"]) < 100 else "可持續觀察此差異",
            })
    warning = "" if impressions >= 100 else "目前樣本少於 100 次有效曝光，成效趨勢僅供參考。"
    purchase_rate = round(purchases / impressions, 4) if impressions else 0.0
    ignore_rate = round(len(ignored_keys) / impressions, 4) if impressions else 0.0
    return EffectivenessReport(
        filters=active_filters,
        impressions=impressions,
        clicks=len(click_keys),
        add_to_carts=len(add_keys),
        purchases=purchases,
        ignored=len(ignored_keys),
        click_through_rate=round(len(click_keys) / impressions, 4) if impressions else 0.0,
        add_to_cart_rate=round(len(add_keys) / impressions, 4) if impressions else 0.0,
        purchase_rate=purchase_rate,
        ignore_rate=ignore_rate,
        attributed_revenue=sum(max(0, int(row.get("attributed_revenue") or 0)) for row in confirmed),
        attributed_discount=sum(max(0, int(row.get("attributed_discount") or 0)) for row in confirmed),
        provisional_attributions=sum(1 for row in scoped_attributions if row.get("status") == "provisional"),
        incomplete_events=incomplete,
        sample_warning=warning,
        breakdowns=breakdowns,
        comparisons=comparison_rows,
    )
