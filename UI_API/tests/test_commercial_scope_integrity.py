from __future__ import annotations

from uuid import UUID

import pytest


def test_scoped_repositories_share_one_conflict_error_type() -> None:
    from models.commercial_scope import CommercialScopeConflictError
    from repositories import (
        admin_audit_repository,
        member_repository,
        member_session_repository,
        recommendation_event_repository,
    )

    assert member_repository.CommercialScopeConflictError is CommercialScopeConflictError
    assert member_session_repository.CommercialScopeConflictError is CommercialScopeConflictError
    assert admin_audit_repository.CommercialScopeConflictError is CommercialScopeConflictError
    assert recommendation_event_repository.CommercialScopeConflictError is CommercialScopeConflictError


def test_postgres_json_fallback_is_never_available() -> None:
    from repositories import postgres_utils

    assert postgres_utils.allow_postgres_json_fallback() is False


def test_production_rejects_postgres_json_fallback_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    import config

    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setenv("ALLOW_POSTGRES_JSON_FALLBACK", "true")

    with pytest.raises(RuntimeError, match="ALLOW_POSTGRES_JSON_FALLBACK"):
        config.validate_startup_config()


def test_postgres_read_and_write_fail_closed_without_json_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from repositories import member_repository, postgres_utils

    monkeypatch.setattr(member_repository.postgres_utils, "use_postgres", lambda: True)
    monkeypatch.setattr(member_repository, "_postgres_get_member", lambda *_args: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(
        member_repository, "_postgres_upsert_member", lambda *_args: (_ for _ in ()).throw(RuntimeError())
    )
    monkeypatch.setattr(member_repository, "_read", lambda: (_ for _ in ()).throw(AssertionError("JSON read")))
    monkeypatch.setattr(member_repository, "_write", lambda _rows: (_ for _ in ()).throw(AssertionError("JSON write")))
    monkeypatch.setattr(postgres_utils, "allow_postgres_json_fallback", lambda: False)

    with pytest.raises(postgres_utils.PostgresOperationError):
        member_repository.get_member_scoped("0912345678", LEGACY_DEFAULT_SCOPE)
    with pytest.raises(postgres_utils.PostgresOperationError):
        member_repository.upsert_member_scoped({"phone": "0912345678"}, LEGACY_DEFAULT_SCOPE)


def test_development_database_failure_never_falls_back_to_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE, CommercialScopeConflictError
    from repositories import postgres_utils, recommendation_event_repository

    monkeypatch.setattr(recommendation_event_repository.postgres_utils, "use_postgres", lambda: True)
    monkeypatch.setattr(postgres_utils, "allow_postgres_json_fallback", lambda: False)
    monkeypatch.setattr(
        recommendation_event_repository, "_postgres_get_events", lambda *_args: (_ for _ in ()).throw(RuntimeError())
    )
    monkeypatch.setattr(
        recommendation_event_repository,
        "_read_list",
        lambda _path: (_ for _ in ()).throw(AssertionError("JSON fallback must not run")),
    )

    with pytest.raises(postgres_utils.PostgresOperationError):
        recommendation_event_repository.get_recommendation_events_scoped(LEGACY_DEFAULT_SCOPE)

    monkeypatch.setattr(
        recommendation_event_repository,
        "_postgres_append_events",
        lambda *_args: (_ for _ in ()).throw(CommercialScopeConflictError("collision")),
    )
    with pytest.raises(CommercialScopeConflictError):
        recommendation_event_repository.append_recommendation_event_scoped({"event_id": "shared"}, LEGACY_DEFAULT_SCOPE)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (None, "tenant"),
        (
            {
                "tenant_status": "inactive",
                "store_tenant_id": UUID(int=1),
                "store_status": "active",
                "device_tenant_id": UUID(int=1),
                "device_store_id": UUID(int=2),
                "device_status": "active",
            },
            "tenant",
        ),
        (
            {
                "tenant_status": "active",
                "store_tenant_id": UUID(int=2),
                "store_status": "active",
                "device_tenant_id": UUID(int=1),
                "device_store_id": UUID(int=2),
                "device_status": "active",
            },
            "store",
        ),
        (
            {
                "tenant_status": "active",
                "store_tenant_id": UUID(int=1),
                "store_status": "active",
                "device_tenant_id": UUID(int=1),
                "device_store_id": UUID(int=3),
                "device_status": "active",
            },
            "device",
        ),
        (
            {
                "tenant_status": "active",
                "store_tenant_id": UUID(int=1),
                "store_status": "active",
                "device_tenant_id": UUID(int=1),
                "device_store_id": UUID(int=2),
                "device_status": "inactive",
            },
            "device",
        ),
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


def test_integrity_validator_emits_only_aggregate_machine_readable_counts(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
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
