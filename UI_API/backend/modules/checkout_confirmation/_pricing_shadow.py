"""Non-blocking cutover comparison for pricing and measurement paths."""

from __future__ import annotations

from capabilities.operations_configuration import interface as _operations

observability_service = _operations.observability_service


def compare_pricing(
    *,
    preferred_ref: str,
    legacy_ref: str,
    legacy_effective_price: int,
    selected_ref: str,
    selected_effective_price: int,
    base_price: int,
) -> dict:
    """Classify legacy-vs-new pricing without changing the selected customer price."""

    if not preferred_ref and selected_effective_price < base_price:
        classification = "expected_automatic_discount"
    elif preferred_ref and selected_effective_price < legacy_effective_price:
        classification = "expected_customer_best_price"
    elif legacy_ref == selected_ref and legacy_effective_price == selected_effective_price:
        classification = "match"
    else:
        classification = "unexpected_mismatch"
    observability_service.increment_metric("promotion_shadow_comparisons_total", status=classification)
    if classification == "unexpected_mismatch":
        observability_service.increment_metric("promotion_shadow_unexpected_mismatches_total")
    return {
        "classification": classification,
        "legacy_ref": legacy_ref,
        "legacy_effective_price": legacy_effective_price,
        "selected_ref": selected_ref,
        "selected_effective_price": selected_effective_price,
    }


def measurement_shadow_report(new_report, legacy_events: list[dict]) -> dict:
    legacy_counts = {
        "impressions": sum(1 for row in legacy_events if row.get("event_type") == "recommendation_shown"),
        "clicks": sum(1 for row in legacy_events if row.get("event_type") == "recommendation_clicked"),
        "add_to_carts": sum(1 for row in legacy_events if row.get("event_type") == "recommendation_added_to_cart"),
        "purchases": sum(1 for row in legacy_events if row.get("event_type") == "recommendation_checked_out"),
    }
    new_counts = {key: int(getattr(new_report, key, 0)) for key in legacy_counts}
    return {
        "new_unique_counts": new_counts,
        "legacy_raw_counts": legacy_counts,
        "differences": {key: new_counts[key] - legacy_counts[key] for key in legacy_counts},
        "unexpected_price_mismatches": observability_service.metrics_snapshot()
        .get("promotion_shadow_unexpected_mismatches_total", {})
        .get("total", 0),
        "event_data_ready": new_report.impressions >= 100 and new_report.incomplete_events == 0,
        "pricing_ready": observability_service.metrics_snapshot()
        .get("promotion_shadow_unexpected_mismatches_total", {})
        .get("total", 0)
        == 0,
    }
