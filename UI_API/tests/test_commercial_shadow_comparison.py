from services import commercial_shadow_service, observability_service


def test_shadow_comparison_separates_expected_cutover_from_mismatch():
    observability_service.reset_metrics_for_tests()

    automatic = commercial_shadow_service.compare_pricing(
        preferred_ref="", legacy_ref="", legacy_effective_price=100,
        selected_ref="campaign-a", selected_effective_price=80, base_price=100,
    )
    match = commercial_shadow_service.compare_pricing(
        preferred_ref="campaign-a", legacy_ref="campaign-a", legacy_effective_price=80,
        selected_ref="campaign-a", selected_effective_price=80, base_price=100,
    )

    assert automatic["classification"] == "expected_automatic_discount"
    assert match["classification"] == "match"
    assert observability_service.metrics_snapshot()["promotion_shadow_unexpected_mismatches_total"] == {}
