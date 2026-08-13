"""Contract evidence for Recommendation's interaction and analytics surfaces."""

import pytest

from modules.analytics.application import build_effectiveness_report
from modules.recommendation import _experiment_service as experiment_service
from modules.recommendation._interaction_event import normalize_interaction_event
from modules.recommendation._intervention import decide_intervention

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_experiment_assignment_is_disabled_until_both_switches_are_ready(monkeypatch):
    values = {
        "RECOMMENDATION_EXPERIMENT_ENABLED": True,
        "RECOMMENDATION_EXPERIMENT_CONFIGURED": False,
    }
    monkeypatch.setattr(experiment_service.config, "get", lambda key, default=None: values.get(key, default))

    assignment = experiment_service.assign("session-1", "experiment-1")

    assert assignment == {
        "enabled": False,
        "experiment_id": "",
        "variant_id": "",
        "strategy": "weighted_random",
    }


def test_enabled_experiment_assignment_is_deterministic_for_a_session(monkeypatch):
    values = {
        "RECOMMENDATION_EXPERIMENT_ENABLED": True,
        "RECOMMENDATION_EXPERIMENT_CONFIGURED": True,
        "RECOMMENDATION_EXPERIMENT_VARIANTS": [
            {"variant_id": "control", "strategy": "weighted_random", "traffic": 50},
            {"variant_id": "ranked", "strategy": "ranked_top_score", "traffic": 50},
        ],
    }
    monkeypatch.setattr(experiment_service.config, "get", lambda key, default=None: values.get(key, default))

    first = experiment_service.assign("session-1", "experiment-1")
    second = experiment_service.assign("session-1", "experiment-1")

    assert first == second
    assert first["enabled"] is True
    assert first["experiment_id"] == "experiment-1"
    assert first["variant_id"] in {"control", "ranked"}


def test_interaction_event_normalization_preserves_context_and_clamps_metrics():
    event = normalize_interaction_event(
        {
            "session_id": "session-1",
            "page_id": "payment",
            "event_type": "payment_error",
            "metadata": {"dwell_time_sec": -4, "back_count": "3"},
            "ui_context": {"step": "payment"},
            "payment_fail_count": "2.7",
            "invalid_touch_count": -1,
        }
    )

    assert event["session_id"] == "session-1"
    assert event["metadata"] == {"dwell_time_sec": -4, "back_count": "3"}
    assert event["ui_context"] == {"step": "payment"}
    assert event["dwell_time_sec"] == 0.0
    assert event["back_count"] == 3
    assert event["payment_fail_count"] == 2
    assert event["invalid_touch_count"] == 0
    assert event["category_switch_count"] == 0


def test_payment_confusion_with_repeated_failures_calls_staff_and_disables_promotion():
    intervention = decide_intervention(
        {"barrier_state": "payment_confusion", "severity": 0.8, "payment_fail_count": 2},
        {"page_id": "payment"},
    )

    assert intervention["action"] == "call_staff"
    assert intervention["action_level"] == "high"
    assert intervention["staff_notify"] is True
    assert intervention["ui_patch"]["disable_promotion"] is True
    assert intervention["ui_context"] == {"page_id": "payment"}


def test_normal_operation_does_not_intervene():
    intervention = decide_intervention({"barrier_state": "normal_operation"})

    assert intervention["action"] == "none"
    assert intervention["action_level"] == "none"
    assert intervention["staff_notify"] is False


def test_effectiveness_report_deduplicates_touch_ids_and_scopes_attribution():
    events = [
        {
            "type": "commercial_touch.impression",
            "event_id": "event-imp-1",
            "payload": {
                "impression_id": "imp-1",
                "variant_id": "control",
                "data_quality": "complete",
                "store_id": "store-1",
            },
        },
        {
            "type": "commercial_touch.impression",
            "event_id": "event-imp-1-duplicate",
            "payload": {
                "impression_id": "imp-1",
                "variant_id": "control",
                "data_quality": "complete",
                "store_id": "store-1",
            },
        },
        {
            "type": "commercial_touch.click",
            "event_id": "event-click-1",
            "payload": {
                "impression_id": "imp-1",
                "variant_id": "control",
                "data_quality": "complete",
                "store_id": "store-1",
            },
        },
        {
            "type": "commercial_touch.add_to_cart",
            "event_id": "event-add-1",
            "payload": {
                "impression_id": "imp-1",
                "variant_id": "control",
                "data_quality": "complete",
                "store_id": "store-1",
            },
        },
        {
            "type": "commercial_touch.ignore",
            "event_id": "event-ignore-1",
            "payload": {
                "impression_id": "imp-1",
                "variant_id": "control",
                "data_quality": "complete",
                "store_id": "store-1",
            },
        },
        {
            "type": "commercial_touch.impression",
            "event_id": "event-imp-2",
            "payload": {
                "impression_id": "imp-2",
                "variant_id": "ranked",
                "data_quality": "complete",
                "store_id": "store-1",
            },
        },
        {
            "type": "commercial_touch.impression",
            "event_id": "event-imp-3",
            "payload": {
                "impression_id": "imp-3",
                "variant_id": "ranked",
                "data_quality": "partial",
                "store_id": "store-1",
            },
        },
        {
            "type": "commercial_touch.impression",
            "event_id": "event-imp-out",
            "payload": {"impression_id": "imp-out", "variant_id": "control", "store_id": "store-2"},
        },
    ]
    attributions = [
        {
            "impression_id": "imp-1",
            "order_item_id": "order-item-1",
            "status": "confirmed",
            "attributed_revenue": 120,
            "attributed_discount": 10,
        },
        {"impression_id": "imp-2", "status": "provisional", "attributed_revenue": 50},
        {"impression_id": "imp-out", "order_item_id": "order-item-out", "status": "confirmed"},
    ]

    report = build_effectiveness_report(events, attributions, filters={"store_id": "store-1"})

    assert report.filters == {"store_id": "store-1"}
    assert report.impressions == 3
    assert report.clicks == 1
    assert report.add_to_carts == 1
    assert report.purchases == 1
    assert report.ignored == 1
    assert report.attributed_revenue == 120
    assert report.attributed_discount == 10
    assert report.provisional_attributions == 1
    assert report.incomplete_events == 1
    assert report.sample_warning
    assert report.breakdowns == [
        {"variant_id": "control", "impressions": 1, "clicks": 1, "add_to_carts": 1},
        {"variant_id": "ranked", "impressions": 2, "clicks": 0, "add_to_carts": 0},
    ]
    assert report.comparisons[0]["variant_id"] == "ranked"
    assert report.comparisons[0]["conclusion"] == "樣本不足，僅顯示觀察差異"
