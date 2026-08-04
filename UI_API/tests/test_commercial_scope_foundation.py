from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "UI_API/backend/schemas/migrations/0002_commercial_scope_foundation.sql"


def test_reserved_default_scope_ids_are_stable_and_distinct() -> None:
    from models.commercial_scope import (
        LEGACY_DEFAULT_DEVICE_ID,
        LEGACY_DEFAULT_STORE_ID,
        LEGACY_DEFAULT_TENANT_ID,
    )

    assert LEGACY_DEFAULT_TENANT_ID == UUID("00000000-0000-4000-8000-000000000001")
    assert LEGACY_DEFAULT_STORE_ID == UUID("00000000-0000-4000-8000-000000000002")
    assert LEGACY_DEFAULT_DEVICE_ID == UUID("00000000-0000-4000-8000-000000000003")
    assert len({LEGACY_DEFAULT_TENANT_ID, LEGACY_DEFAULT_STORE_ID, LEGACY_DEFAULT_DEVICE_ID}) == 3


def test_new_commercial_records_use_application_uuid4() -> None:
    from models.commercial_scope import new_commercial_id

    assert new_commercial_id().version == 4


def test_commercial_scope_exposes_tenant_store_and_device_boundaries() -> None:
    from models.commercial_scope import CommercialScope

    scope = CommercialScope(
        tenant_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        store_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        device_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
    )

    assert scope.tenant_scope.tenant_id == scope.tenant_id
    assert scope.store_scope.store_id == scope.store_id
    assert scope.device_scope is not None
    assert scope.device_scope.device_id == scope.device_id

    with pytest.raises(TypeError, match="tenant_id"):
        CommercialScope(cast(UUID, "tenant"), scope.store_id)


def test_default_scope_resolver_validates_uuid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import commercial_scope_service

    scope_config = commercial_scope_service.commercial_scope_config
    monkeypatch.setattr(scope_config.config, "is_production", lambda: False)
    monkeypatch.setattr(
        scope_config.config,
        "get",
        lambda key, default=None: "not-a-uuid" if key == "DEFAULT_STORE_ID" else default,
    )

    with pytest.raises(commercial_scope_service.CommercialScopeConfigurationError, match="DEFAULT_STORE_ID"):
        commercial_scope_service.resolve_commercial_scope()


def test_production_scope_configuration_fails_fast_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import commercial_scope_service

    scope_config = commercial_scope_service.commercial_scope_config
    monkeypatch.setattr(scope_config.config, "is_production", lambda: True)
    monkeypatch.setattr(scope_config.config, "get", lambda _key, default=None: default)

    with pytest.raises(commercial_scope_service.CommercialScopeConfigurationError, match="production"):
        commercial_scope_service.resolve_commercial_scope()


def test_unverified_scope_headers_cannot_override_server_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from services import commercial_scope_service

    scope_config = commercial_scope_service.commercial_scope_config
    monkeypatch.setattr(scope_config.config, "is_production", lambda: False)
    monkeypatch.setattr(scope_config.config, "get", lambda _key, default=None: default)

    scope = commercial_scope_service.resolve_commercial_scope(
        {
            "X-Tenant-ID": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "X-Store-ID": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "X-Device-ID": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        }
    )

    assert scope == LEGACY_DEFAULT_SCOPE


def test_migration_defines_scope_hierarchy_and_expand_columns() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for table in ("tenants", "stores", "devices"):
        assert f"CREATE TABLE {table}" in sql
    assert "FOREIGN KEY (store_id, tenant_id)" in sql
    assert "REFERENCES stores(id, tenant_id)" in sql
    assert "FOREIGN KEY (origin_device_id, store_id, tenant_id)" in sql
    assert "REFERENCES devices(id, store_id, tenant_id)" in sql
    assert "ALTER TABLE members ADD COLUMN IF NOT EXISTS tenant_id UUID" in sql
    assert "ALTER TABLE member_sessions ADD COLUMN IF NOT EXISTS store_id UUID" in sql
    assert "ALTER TABLE member_orders ADD COLUMN IF NOT EXISTS origin_device_id UUID" in sql
    assert "ALTER TABLE recommendation_events ADD COLUMN IF NOT EXISTS device_id UUID" in sql
    assert "ALTER TABLE admin_audit_logs ADD COLUMN IF NOT EXISTS store_id UUID" in sql
    assert "ALTER COLUMN tenant_id SET NOT NULL" not in sql


def test_migration_does_not_modify_member_identity_or_require_extensions() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "create extension" not in sql
    assert "drop constraint" not in sql
    assert "drop column" not in sql
    assert "alter column phone" not in sql


def test_legacy_repository_methods_delegate_to_default_scope() -> None:
    member_source = (ROOT / "UI_API/backend/repositories/member_repository.py").read_text(encoding="utf-8")
    session_source = (ROOT / "UI_API/backend/repositories/member_session_repository.py").read_text(encoding="utf-8")
    event_source = (ROOT / "UI_API/backend/repositories/recommendation_event_repository.py").read_text(encoding="utf-8")

    assert "def get_member_scoped(" in member_source
    assert "resolve_commercial_scope()" in member_source
    assert "def get_session_phone_scoped(" in session_source
    assert "resolve_commercial_scope()" in session_source
    assert "def get_recommendation_events_scoped(" in event_source
    assert "resolve_commercial_scope()" in event_source


def test_environment_example_documents_default_scope() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "DEFAULT_TENANT_ID=00000000-0000-4000-8000-000000000001" in env_example
    assert "DEFAULT_STORE_ID=00000000-0000-4000-8000-000000000002" in env_example
    assert "DEFAULT_DEVICE_ID=00000000-0000-4000-8000-000000000003" in env_example
