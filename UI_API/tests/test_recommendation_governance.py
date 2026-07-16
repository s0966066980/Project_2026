"""Milestone 3D promotion/recommendation governance contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")


def test_strategy_publish_pause_rollback(tmp_path, monkeypatch) -> None:
    from services import recommendation_governance_service

    monkeypatch.setattr(recommendation_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    v1 = recommendation_governance_service.create_strategy_draft(
        strategy_id="banner-main",
        eligibility={"days_of_week": [0, 1, 2, 3, 4, 5, 6]},
        ranking_config={"algo": "popularity"},
        tenant_id=TENANT,
        store_id=STORE,
    )
    recommendation_governance_service.submit_strategy("banner-main", v1.version)
    published = recommendation_governance_service.publish_strategy("banner-main", v1.version)
    assert published.status.value == "published"
    v2 = recommendation_governance_service.create_strategy_draft(
        strategy_id="banner-main",
        eligibility={},
        ranking_config={"algo": "ctr"},
        tenant_id=TENANT,
        store_id=STORE,
    )
    recommendation_governance_service.publish_strategy("banner-main", v2.version)
    restored = recommendation_governance_service.rollback_strategy("banner-main", v1.version)
    assert restored.version == v1.version
    assert restored.status.value == "published"


def test_eligibility_respects_scope_timezone_and_window(tmp_path, monkeypatch) -> None:
    from models.recommendation_governance import StrategyStatus, StrategyVersion
    from services import recommendation_governance_service

    monkeypatch.setattr(recommendation_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    published = StrategyVersion(
        strategy_id="lunch",
        version=1,
        status=StrategyStatus.PUBLISHED,
        scope_tenant_id=TENANT,
        scope_store_id=STORE,
        eligibility={"days_of_week": [0]},  # Monday
        ranking_config={},
        effective_from="2026-01-01T00:00:00+00:00",
        effective_to="2026-12-31T00:00:00+00:00",
    )
    monday = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)  # Monday
    assert recommendation_governance_service.is_eligible(published, tenant_id=TENANT, store_id=STORE, now=monday)
    other_store = UUID("00000000-0000-4000-8000-000000000099")
    assert not recommendation_governance_service.is_eligible(
        published, tenant_id=TENANT, store_id=other_store, now=monday
    )


def test_experiment_assignment_is_deterministic() -> None:
    from services import recommendation_governance_service

    first = recommendation_governance_service.assign_experiment_variant(
        experiment_id="exp-1",
        assignment_key="session-a",
        variants=["A", "B"],
    )
    second = recommendation_governance_service.assign_experiment_variant(
        experiment_id="exp-1",
        assignment_key="session-a",
        variants=["A", "B"],
    )
    assert first.variant == second.variant
    assert first.deterministic is True


def test_event_idempotency_and_data_quality(tmp_path, monkeypatch) -> None:
    from models.recommendation_governance import RecommendationEventRecord
    from services import recommendation_governance_service

    monkeypatch.setattr(recommendation_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    exposure = RecommendationEventRecord(
        event_id="e1",
        strategy_version="banner-main@v1",
        experiment_id="exp-1",
        variant="A",
        tenant_id=TENANT,
        store_id=STORE,
        session_ref="s1",
        member_ref="m-opaque",
        surface="kiosk_home",
        rank=1,
        score=0.8,
        reason_code="popular",
        timestamp="2026-07-13T00:00:00+00:00",
        event_type="exposure",
    )
    recommendation_governance_service.record_event(exposure)
    recommendation_governance_service.record_event(exposure)  # idempotent
    recommendation_governance_service.record_event(
        RecommendationEventRecord(
            event_id="e2",
            strategy_version="banner-main@v1",
            experiment_id="exp-1",
            variant="A",
            tenant_id=TENANT,
            store_id=STORE,
            session_ref="s1",
            member_ref="m-opaque",
            surface="kiosk_home",
            rank=1,
            score=0.8,
            reason_code="popular",
            timestamp="2026-07-13T00:01:00+00:00",
            event_type="conversion",
        )
    )
    report = recommendation_governance_service.data_quality_report()
    assert report["total_events"] == 2
    assert report["duplicate_event_ids"] == 0
    assert report["conversion_with_prior_exposure"] == 1
    assert report["conversion_without_exposure"] == 0
