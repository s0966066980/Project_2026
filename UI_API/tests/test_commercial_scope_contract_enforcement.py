"""Milestone 1E commercial scope contract enforcement guarantees."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_contract_migration_enforces_core_scope_and_adds_operational_tables() -> None:
    path = ROOT / "UI_API/backend/schemas/migrations/0005_commercial_scope_contract_enforcement.sql"
    sql = path.read_text(encoding="utf-8")

    for fragment in (
        "ALTER TABLE members ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE member_sessions ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE member_sessions ALTER COLUMN store_id SET NOT NULL",
        "ALTER TABLE member_sessions ALTER COLUMN origin_device_id SET NOT NULL",
        "ALTER TABLE member_orders ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE recommendation_events ALTER COLUMN device_id SET NOT NULL",
        "ALTER TABLE admin_audit_logs ALTER COLUMN tenant_id SET NOT NULL",
    ):
        assert fragment in sql
    for table in (
        "store_availability",
        "commercial_settings_versions",
        "promotion_records",
        "interaction_events",
        "intervention_outcomes",
        "rag_asset_scopes",
    ):
        assert f"CREATE TABLE {table}" in sql
    assert "ALTER TABLE admin_audit_logs ALTER COLUMN store_id SET NOT NULL" not in sql


def test_verified_principals_are_the_only_identity_to_scope_adapters() -> None:
    from models.admin_identity import AdminPrincipal
    from models.commercial_scope import CommercialScope
    from models.device_identity import DevicePrincipal
    from services.commercial_context_service import scope_from_admin_principal, scope_from_device_principal

    admin_annotations = scope_from_admin_principal.__annotations__
    device_annotations = scope_from_device_principal.__annotations__
    assert admin_annotations["principal"] is AdminPrincipal
    assert device_annotations["principal"] is DevicePrincipal
    assert admin_annotations["return"] is CommercialScope
    assert device_annotations["return"] is CommercialScope


def test_operational_repositories_expose_explicit_scoped_methods() -> None:
    expectations = {
        "availability_repository.py": ("get_availability_scoped", "save_availability_scoped"),
        "interaction_event_repository.py": (
            "append_interaction_event_scoped",
            "get_interaction_events_scoped",
            "append_intervention_log_scoped",
            "update_intervention_result_scoped",
        ),
        "promotion_repository.py": ("list_promotions_scoped", "save_promotion_scoped"),
        "commercial_settings_repository.py": ("get_settings_scoped", "save_settings_scoped"),
    }
    root = ROOT / "UI_API/backend/repositories"
    for filename, methods in expectations.items():
        source = (root / filename).read_text(encoding="utf-8")
        for method in methods:
            assert f"def {method}(" in source, (filename, method)


def test_scope_integrity_validator_covers_operational_tables() -> None:
    source = (ROOT / "UI_API/backend/scripts/validate_commercial_scope.py").read_text(encoding="utf-8")
    for table in (
        "store_availability",
        "commercial_settings_versions",
        "promotion_records",
        "interaction_events",
        "intervention_outcomes",
        "rag_asset_scopes",
    ):
        assert table in source


def test_no_new_production_route_uses_unscoped_operational_repository_calls() -> None:
    routes = ROOT / "UI_API/backend/routes"
    forbidden = (
        "availability_repository.get_availability(",
        "availability_repository.save_availability(",
        "interaction_event_repository.append_interaction_event(",
        "promotion_repository.list_promotions(",
    )
    offenders: list[str] = []
    for path in routes.glob("*_routes.py"):
        source = path.read_text(encoding="utf-8")
        if any(call in source for call in forbidden):
            offenders.append(path.name)
    assert offenders == []
