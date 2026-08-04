from uuid import UUID

import pytest


def _scope():
    from models.commercial_scope import CommercialScope

    return CommercialScope(
        tenant_id=UUID("00000000-0000-4000-8000-000000000010"),
        store_id=UUID("00000000-0000-4000-8000-000000000020"),
        device_id=UUID("00000000-0000-4000-8000-000000000030"),
    )


def test_touch_receipt_is_idempotent_and_scoped():
    from modules.analytics.application import record_touch
    from services.analytics_pipeline_service import InMemoryAnalyticsSink

    sink = InMemoryAnalyticsSink()
    payload = {
        "event_id": "evt-visible-1",
        "event_type": "impression",
        "decision_id": "decision-1",
        "impression_id": "impression-1",
        "placement": "recommendation_card",
        "item_id": "MCD012",
    }

    first = record_touch(payload, _scope(), sink=sink)
    duplicate = record_touch(payload, _scope(), sink=sink)

    assert first.accepted is True
    assert duplicate.accepted is False
    assert duplicate.duplicate is True
    assert sink.events[0]["payload"]["decision_id"] == "decision-1"


def test_touch_rejects_scope_conflicts_and_secrets():
    from modules.analytics.application import TouchValidationError, record_touch
    from services.analytics_pipeline_service import InMemoryAnalyticsSink

    with pytest.raises(TouchValidationError, match="scope_mismatch"):
        record_touch({
            "event_id": "evt-wrong-scope",
            "event_type": "click",
            "decision_id": "decision-1",
            "impression_id": "impression-1",
            "tenant_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        }, _scope(), sink=InMemoryAnalyticsSink())

    with pytest.raises(TouchValidationError, match="forbidden"):
        record_touch({
            "event_id": "evt-secret",
            "event_type": "click",
            "decision_id": "decision-1",
            "impression_id": "impression-1",
            "metadata": {"auth_token": "never-store"},
        }, _scope(), sink=InMemoryAnalyticsSink())


def test_legacy_touch_is_marked_incomplete_instead_of_inventing_ids():
    from modules.analytics.application import record_touch
    from services.analytics_pipeline_service import InMemoryAnalyticsSink

    sink = InMemoryAnalyticsSink()
    receipt = record_touch({
        "event_id": "evt-legacy",
        "event_type": "recommendation_shown",
        "item_id": "MCD012",
    }, _scope(), sink=sink)

    assert receipt.accepted is True
    assert sink.events[0]["payload"]["data_quality"] == "legacy_missing_touch_ids"
