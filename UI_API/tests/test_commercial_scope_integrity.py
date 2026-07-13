from __future__ import annotations

from contextlib import nullcontext
from uuid import UUID

import pytest


def test_scoped_repositories_share_one_conflict_error_type() -> None:
    from models.commercial_scope import CommercialScopeConflictError
    from repositories import admin_audit_repository, member_repository, recommendation_event_repository

    assert member_repository.CommercialScopeConflictError is CommercialScopeConflictError
    assert admin_audit_repository.CommercialScopeConflictError is CommercialScopeConflictError
    assert recommendation_event_repository.CommercialScopeConflictError is CommercialScopeConflictError


@pytest.mark.parametrize(
    ("app_env", "fallback", "expected"),
    [
        ("development", True, True),
        ("development", False, False),
        ("staging", True, False),
        ("production", False, False),
    ],
)
def test_postgres_json_fallback_requires_explicit_development_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    fallback: bool,
    expected: bool,
) -> None:
    from repositories import postgres_utils

    monkeypatch.setattr(postgres_utils.config, "APP_ENV", app_env)
    monkeypatch.setattr(
        postgres_utils.config,
        "get",
        lambda key, default=None: fallback if key == "ALLOW_POSTGRES_JSON_FALLBACK" else default,
    )

    assert postgres_utils.allow_postgres_json_fallback() is expected


def test_production_rejects_postgres_json_fallback_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    import config

    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setenv("ALLOW_POSTGRES_JSON_FALLBACK", "true")

    with pytest.raises(RuntimeError, match="ALLOW_POSTGRES_JSON_FALLBACK"):
        config.validate_startup_config()


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (None, "tenant"),
        ({"tenant_status": "inactive", "store_tenant_id": UUID(int=1), "store_status": "active", "device_tenant_id": UUID(int=1), "device_store_id": UUID(int=2), "device_status": "active"}, "tenant"),
        ({"tenant_status": "active", "store_tenant_id": UUID(int=2), "store_status": "active", "device_tenant_id": UUID(int=1), "device_store_id": UUID(int=2), "device_status": "active"}, "store"),
        ({"tenant_status": "active", "store_tenant_id": UUID(int=1), "store_status": "active", "device_tenant_id": UUID(int=1), "device_store_id": UUID(int=3), "device_status": "active"}, "device"),
        ({"tenant_status": "active", "store_tenant_id": UUID(int=1), "store_status": "active", "device_tenant_id": UUID(int=1), "device_store_id": UUID(int=2), "device_status": "inactive"}, "device"),
    ],
)
def test_configured_scope_readiness_rejects_missing_inactive_or_mismatched_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, object] | None,
    message: str,
) -> None:
    from models.commercial_scope import CommercialScope
    from services import commercial_scope_readiness_service

    scope = CommercialScope(UUID(int=1), UUID(int=2), UUID(int=3))

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _sql: str, _params: tuple[object, ...]) -> None:
            return None

        def fetchone(self):
            return row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self):
            return Cursor()

    monkeypatch.setattr(commercial_scope_readiness_service.postgres_utils, "connect", lambda: Connection())

    with pytest.raises(commercial_scope_readiness_service.CommercialScopeReadinessError, match=message):
        commercial_scope_readiness_service.validate_configured_commercial_scope(scope)


def test_configured_scope_readiness_returns_typed_result_for_active_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from models.commercial_scope import CommercialScope
    from services import commercial_scope_readiness_service

    scope = CommercialScope(UUID(int=1), UUID(int=2), UUID(int=3))
    row = {
        "tenant_status": "active",
        "store_tenant_id": scope.tenant_id,
        "store_status": "active",
        "device_tenant_id": scope.tenant_id,
        "device_store_id": scope.store_id,
        "device_status": "active",
    }

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _sql: str, _params: tuple[object, ...]) -> None:
            return None

        def fetchone(self):
            return row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self):
            return Cursor()

    monkeypatch.setattr(commercial_scope_readiness_service.postgres_utils, "connect", lambda: Connection())

    result = commercial_scope_readiness_service.validate_configured_commercial_scope(scope)

    assert result.scope == scope
    assert result.is_ready is True


def test_integrity_validator_emits_only_aggregate_machine_readable_counts(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from backend.scripts import validate_commercial_scope

    monkeypatch.setattr(
        validate_commercial_scope,
        "collect_violations",
        lambda: [("member_sessions", "missing_device_scope", 2)],
    )

    assert validate_commercial_scope.main(["--require-complete"]) == 1
    output = capsys.readouterr().out
    assert '"table": "member_sessions"' in output
    assert '"count": 2' in output
    assert "091" not in output
