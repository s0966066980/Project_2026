from modules.analytics import build_effectiveness_report


def _event(event_id: str, event_type: str, impression_id: str, *, variant: str = "A", quality: str = "complete"):
    return {
        "event_id": event_id,
        "type": f"commercial_touch.{event_type}",
        "occurred_at": "2026-07-14T10:00:00+00:00",
        "payload": {
            "impression_id": impression_id,
            "variant_id": variant,
            "placement": "首頁推薦",
            "data_quality": quality,
        },
    }


def test_effectiveness_report_deduplicates_funnel_and_uses_confirmed_revenue():
    events = [
        _event("e1", "impression", "imp-1"),
        _event("e1-copy", "impression", "imp-1"),
        _event("e2", "click", "imp-1"),
        _event("e3", "add_to_cart", "imp-1"),
        _event("e3-ignore", "ignore", "imp-2"),
        _event("e4", "impression", "imp-2", quality="legacy_missing_touch_ids"),
    ]
    attributions = [
        {
            "order_item_id": 10,
            "impression_id": "imp-1",
            "status": "confirmed",
            "attributed_revenue": 120,
            "attributed_discount": 20,
        },
        {
            "order_item_id": 11,
            "impression_id": "imp-2",
            "status": "provisional",
            "attributed_revenue": 80,
            "attributed_discount": 10,
        },
    ]

    report = build_effectiveness_report(events, attributions, filters={"placement": "首頁推薦"})

    assert report.impressions == 2
    assert report.clicks == 1
    assert report.add_to_carts == 1
    assert report.purchases == 1
    assert report.ignored == 1
    assert report.ignore_rate == 0.5
    assert report.attributed_revenue == 120
    assert report.attributed_discount == 20
    assert report.provisional_attributions == 1
    assert report.incomplete_events == 1
    assert report.sample_warning
    assert report.target_status == "insufficient_data"


def test_effectiveness_uses_manager_targets_and_ignore_guardrail():
    events = [
        *[_event(f"impression-{index}", "impression", f"imp-{index}") for index in range(100)],
        *[_event(f"ignored-{index}", "ignore", f"imp-{index}") for index in range(40)],
    ]
    attributions = [
        {
            "order_item_id": index,
            "impression_id": f"imp-{index}",
            "status": "confirmed",
            "attributed_revenue": 100,
            "attributed_discount": 0,
        }
        for index in range(1, 9)
    ]

    report = build_effectiveness_report(
        events,
        attributions,
        targets={
            "RECOMMENDATION_PURCHASE_RATE_TARGET": 0.1,
            "RECOMMENDATION_IGNORE_RATE_GUARDRAIL": 0.35,
        },
    )

    assert report.purchase_rate == 0.08
    assert report.ignore_rate == 0.4
    assert report.purchase_rate_target == 0.1
    assert report.ignore_rate_guardrail == 0.35
    assert report.target_status == "below_target_and_high_ignore"


def test_effectiveness_filters_do_not_mix_variants():
    report = build_effectiveness_report(
        [_event("e1", "impression", "imp-a", variant="A"), _event("e2", "impression", "imp-b", variant="B")],
        [],
        filters={"variant_id": "B"},
    )

    assert report.impressions == 1
    assert report.breakdowns == [{"variant_id": "B", "impressions": 1, "clicks": 0, "add_to_carts": 0}]


def test_effectiveness_compares_variant_with_control_without_infinite_lift():
    report = build_effectiveness_report(
        [_event("e1", "impression", "imp-c", variant="control"), _event("e2", "impression", "imp-b", variant="B")],
        [{"order_item_id": 1, "impression_id": "imp-b", "status": "confirmed", "attributed_revenue": 100, "attributed_discount": 0}],
    )

    assert report.comparisons[0]["purchase_rate_difference"] == 1.0
    assert report.comparisons[0]["relative_lift"] is None
    assert report.comparisons[0]["conclusion"] == "樣本不足，僅顯示觀察差異"
