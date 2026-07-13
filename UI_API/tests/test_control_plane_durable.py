"""Milestones 6B–6D: durable control-plane contracts."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")
DEVICE = UUID("00000000-0000-4000-8000-000000000003")


def test_migration_0011_control_plane_tables() -> None:
    root = Path(__file__).resolve().parents[1]
    sql = (root / "backend/schemas/migrations/0011_control_plane_durable_persistence.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "recommendation_strategies",
        "recommendation_strategy_versions",
        "recommendation_assignments",
        "recommendation_governance_events",
        "promotion_rule_versions",
        "fleet_device_state",
        "fleet_commands",
        "fleet_config_versions",
        "fleet_rollouts",
        "analytics_event_log",
        "analytics_checkpoints",
    ):
        assert f"CREATE TABLE {table}" in sql


def test_recommendation_assignment_is_durable(tmp_path, monkeypatch) -> None:
    from services import recommendation_governance_service

    monkeypatch.setattr(recommendation_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    first = recommendation_governance_service.assign_experiment_variant(
        experiment_id="exp-1",
        assignment_key="session-a",
        variants=["control", "ranked"],
        tenant_id=TENANT,
        store_id=STORE,
        strategy_version=1,
    )
    second = recommendation_governance_service.assign_experiment_variant(
        experiment_id="exp-1",
        assignment_key="session-a",
        variants=["ranked", "control"],  # order flipped must not change assignment
        tenant_id=TENANT,
        store_id=STORE,
        strategy_version=1,
    )
    assert first.variant == second.variant
    assert first.deterministic is True


def test_fleet_heartbeat_json_and_allowlist(tmp_path, monkeypatch) -> None:
    from services import fleet_management_service

    monkeypatch.setattr(fleet_management_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    row = fleet_management_service.heartbeat(
        device_id=DEVICE,
        tenant_id=TENANT,
        store_id=STORE,
        app_version="1.0.0",
        config_version="cfg-1",
    )
    assert row["online"] is True
    with pytest.raises(fleet_management_service.FleetError):
        fleet_management_service.issue_command(
            device_id=DEVICE,
            tenant_id=TENANT,
            command="rm -rf /",
            actor="admin",
            expires_at="2099-01-01T00:00:00+00:00",
        )


def test_analytics_recursive_pii_rejection_and_idempotent_publish(tmp_path, monkeypatch) -> None:
    from services import analytics_pipeline_service

    monkeypatch.setattr(analytics_pipeline_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    with pytest.raises(analytics_pipeline_service.AnalyticsError):
        analytics_pipeline_service.build_envelope(
            event_type="order.completed",
            payload={"nested": {"customer": {"phone": "0912345678"}}},
            tenant_id=TENANT,
            store_id=STORE,
        )
    env = analytics_pipeline_service.build_envelope(
        event_type="order.completed",
        payload={"total": 100, "currency": "TWD"},
        tenant_id=TENANT,
        store_id=STORE,
        event_id="ae_fixed_1",
    )
    sink = analytics_pipeline_service.InMemoryAnalyticsSink()
    assert analytics_pipeline_service.publish(env, sink=sink) is True
    assert analytics_pipeline_service.publish(env, sink=sink) is False
