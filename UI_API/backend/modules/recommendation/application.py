"""Recommendation decisions with durable, caller-stable metadata."""

from __future__ import annotations

from uuid import uuid4

from models.commercial_scope import CommercialScope
from modules.analytics import record_touch
from repositories import recommendation_event_repository
from services import analytics_pipeline_service, recommendation_engine_service

STRATEGY_VERSION = "recommendation-v1"


def list_events(scope: CommercialScope, *, limit: int = 5000) -> list[dict]:
    """Compatibility read behind the Recommendation Application seam."""

    return recommendation_event_repository.get_recommendation_events_scoped(
        scope, "", max(1, min(int(limit), 5000))
    )


def _fallback_items(context: dict, limit: int) -> list[dict]:
    excluded = {str(item_id) for item_id in context.get("controls", {}).get("exclude_item_ids") or []}
    rows = []
    for item in context.get("menu_items") or []:
        item_id = str(item.get("id") or "")
        if not item_id or item_id in excluded:
            continue
        rows.append({**item, "score": 1, "reasons": ["deterministic_fallback"], "offer_ids": [], "offers": []})
        if len(rows) >= limit:
            break
    return rows


def decide(
    context: dict,
    *,
    session_id: str,
    scope: CommercialScope | None = None,
    limit: int = 1,
    randomize: bool = True,
    strategy: str = "",
    experiment: dict | None = None,
    decision_id: str = "",
    sink: analytics_pipeline_service.AnalyticsSinkPort | None = None,
) -> dict:
    experiment_row = experiment if isinstance(experiment, dict) else {}
    resolved_strategy = strategy or str(experiment_row.get("strategy") or "weighted_random")
    fallback_status = "not_used"
    try:
        result = recommendation_engine_service.recommend(
            context,
            limit,
            randomize,
            resolved_strategy,
            experiment_row,
        )
        items = list(result.get("items") or [])
        resolved_strategy = str(result.get("strategy") or resolved_strategy)
    except Exception:
        items = []
    if not items:
        items = _fallback_items(context, limit)
        fallback_status = "engine_fallback"

    resolved_decision_id = decision_id or f"decision_{uuid4().hex}"
    ranked_items = []
    for rank, item in enumerate(items[: max(1, int(limit))], start=1):
        offers = item.get("offers") if isinstance(item.get("offers"), list) else []
        ranked_items.append({
            **item,
            "rank": rank,
            "decision_id": resolved_decision_id,
            "offer_versions": [
                {
                    "offer_id": str(offer.get("offer_id") or ""),
                    "version": int(offer.get("version") or offer.get("campaign_version") or 0),
                }
                for offer in offers
                if isinstance(offer, dict) and str(offer.get("offer_id") or "")
            ],
        })
    decision = {
        "decision_id": resolved_decision_id,
        "strategy": resolved_strategy,
        "strategy_version": STRATEGY_VERSION,
        "experiment_id": str(experiment_row.get("experiment_id") or ""),
        "variant_id": str(experiment_row.get("variant_id") or ""),
        "fallback_status": fallback_status,
        "items": ranked_items,
    }
    if scope is not None:
        record_touch({
            "event_id": f"evt_{resolved_decision_id}",
            "event_type": "decision",
            "decision_id": resolved_decision_id,
            "session_id": session_id,
            "placement": str(context.get("controls", {}).get("surface") or "recommendation"),
            "strategy": resolved_strategy,
            "strategy_version": STRATEGY_VERSION,
            "experiment_id": decision["experiment_id"],
            "variant_id": decision["variant_id"],
            "fallback_status": fallback_status,
            "metadata": {
                "candidates": [
                    {"item_id": str(item.get("id") or ""), "rank": item.get("rank", 0)}
                    for item in ranked_items
                ],
            },
        }, scope, sink=sink)
    return decision
