"""CI-only Milestone 1A -> 1B PostgreSQL upgrade integration tests."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_milestone_1a_database_upgrades_to_scoped_foundation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from repositories import (
        admin_audit_repository,
        member_repository,
        member_session_repository,
        postgres_utils,
        recommendation_event_repository,
    )

    base_url = postgres_utils.database_url()
    schema = "commercial_scope_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')

    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)
    migrations = postgres_utils.migration_files()
    milestone_1a = migrations[0]
    monkeypatch.setattr(postgres_utils, "migration_files", lambda: [milestone_1a])
    postgres_utils.init_schema()

    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        conn.execute(
            "INSERT INTO members (phone, nickname) VALUES (%s, %s)",
            ("0912345678", "Legacy Member"),
        )
        conn.execute(
            "INSERT INTO member_sessions (session_id, phone) VALUES (%s, %s)",
            ("legacy-session", "0912345678"),
        )
        conn.execute(
            "INSERT INTO member_orders (phone, session_id, total) VALUES (%s, %s, %s)",
            ("0912345678", "legacy-session", 120),
        )
        conn.execute(
            "INSERT INTO recommendation_events (event_id, session_id, item_id) VALUES (%s, %s, %s)",
            ("legacy-event", "legacy-session", "item-1"),
        )
        conn.execute(
            "INSERT INTO admin_audit_logs (audit_id, action) VALUES (%s, %s)",
            ("legacy-audit", "legacy"),
        )
        conn.commit()

    monkeypatch.setattr(postgres_utils, "migration_files", lambda: migrations)
    postgres_utils.init_schema()
    first_plan = postgres_utils.get_migration_plan()
    postgres_utils.init_schema()
    second_plan = postgres_utils.get_migration_plan()

    assert first_plan.pending_versions == ()
    assert first_plan.as_dict() == second_plan.as_dict()
    postgres_utils.validate_migration_plan(second_plan, require_clean=True)

    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        default_tenant = conn.execute(
            "SELECT * FROM tenants WHERE id = %s", (LEGACY_DEFAULT_SCOPE.tenant_id,)
        ).fetchone()
        assert default_tenant and default_tenant["code"] == "legacy-default"
        for table, id_column in (
            ("members", "phone"),
            ("member_sessions", "session_id"),
            ("member_orders", "id"),
            ("recommendation_events", "event_id"),
            ("admin_audit_logs", "id"),
        ):
            row = conn.execute(f"SELECT * FROM {table} LIMIT 1").fetchone()
            assert row is not None, (table, id_column)
            assert row["tenant_id"] == LEGACY_DEFAULT_SCOPE.tenant_id
        session = conn.execute("SELECT * FROM member_sessions WHERE session_id = 'legacy-session'").fetchone()
        assert session["store_id"] == LEGACY_DEFAULT_SCOPE.store_id
        assert session["origin_device_id"] == LEGACY_DEFAULT_SCOPE.device_id
        order = conn.execute("SELECT * FROM member_orders LIMIT 1").fetchone()
        event = conn.execute("SELECT * FROM recommendation_events WHERE event_id = 'legacy-event'").fetchone()
        assert order["origin_device_id"] == LEGACY_DEFAULT_SCOPE.device_id
        assert event["device_id"] == LEGACY_DEFAULT_SCOPE.device_id

        tenant_b = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        store_b = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        device_b = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
        conn.execute(
            "INSERT INTO tenants (id, code, name, status) VALUES (%s, %s, %s, %s)",
            (tenant_b, "tenant-b", "Tenant B", "active"),
        )
        conn.execute(
            "INSERT INTO stores (id, tenant_id, code, name, timezone, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (store_b, tenant_b, "store-b", "Store B", "Asia/Taipei", "active"),
        )
        conn.execute(
            "INSERT INTO devices (id, tenant_id, store_id, code, name, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (device_b, tenant_b, store_b, "device-b", "Device B", "active"),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO tenants (id, code, name, status) VALUES (%s, %s, %s, %s)",
                    (UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"), "tenant-b", "Duplicate", "active"),
                )
        with pytest.raises(psycopg.errors.UniqueViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO stores (id, tenant_id, code, name, timezone, status) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
                        tenant_b,
                        "store-b",
                        "Duplicate",
                        "Asia/Taipei",
                        "active",
                    ),
                )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO stores (id, tenant_id, code, name, timezone, status) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
                        UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
                        "orphan",
                        "Orphan",
                        "Asia/Taipei",
                        "active",
                    ),
                )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO devices (id, tenant_id, store_id, code, name, status) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
                        tenant_b,
                        LEGACY_DEFAULT_SCOPE.store_id,
                        "bad",
                        "Bad",
                        "active",
                    ),
                )
        with pytest.raises(psycopg.errors.UniqueViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO devices (id, tenant_id, store_id, code, name, status) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
                        tenant_b,
                        store_b,
                        "device-b",
                        "Duplicate",
                        "active",
                    ),
                )
        conn.execute(
            "INSERT INTO members (id, phone, nickname, tenant_id) VALUES (%s, %s, %s, %s)",
            (uuid4(), "0987654321", "Tenant B Member", tenant_b),
        )
        default_store_b = UUID("11111111-1111-4111-8111-111111111111")
        default_device_b = UUID("22222222-2222-4222-8222-222222222222")
        default_device_c = UUID("33333333-3333-4333-8333-333333333333")
        conn.execute(
            "INSERT INTO stores (id, tenant_id, code, name, timezone, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                default_store_b,
                LEGACY_DEFAULT_SCOPE.tenant_id,
                "legacy-store-b",
                "Default Store B",
                "Asia/Taipei",
                "active",
            ),
        )
        conn.execute(
            "INSERT INTO devices (id, tenant_id, store_id, code, name, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (default_device_b, LEGACY_DEFAULT_SCOPE.tenant_id, default_store_b, "kiosk-b", "Kiosk B", "active"),
        )
        conn.execute(
            "INSERT INTO devices (id, tenant_id, store_id, code, name, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                default_device_c,
                LEGACY_DEFAULT_SCOPE.tenant_id,
                LEGACY_DEFAULT_SCOPE.store_id,
                "kiosk-c",
                "Kiosk C",
                "active",
            ),
        )
        conn.commit()

    default_member = member_repository.get_member_scoped("0912345678", LEGACY_DEFAULT_SCOPE)
    tenant_b_scope = type(LEGACY_DEFAULT_SCOPE)(tenant_b, store_b, device_b)
    assert default_member and default_member["nickname"] == "Legacy Member"
    assert member_repository.get_member_scoped("0912345678", tenant_b_scope) is None
    member_repository.upsert_member_scoped(
        {"phone": "0912345678", "nickname": "Tenant B Same Phone"},
        tenant_b_scope,
    )
    assert member_repository.get_member_scoped("0912345678", LEGACY_DEFAULT_SCOPE)["nickname"] == "Legacy Member"
    assert member_repository.get_member_scoped("0912345678", tenant_b_scope)["nickname"] == "Tenant B Same Phone"
    member_repository.upsert_member_scoped(
        {
            "phone": "0977777777",
            "nickname": "Scoped Order Member",
            "orders": [{"session_id": "tenant-b-order", "total": 88}],
        },
        tenant_b_scope,
    )
    assert member_repository.get_member_scoped("0977777777", tenant_b_scope)["nickname"] == "Scoped Order Member"
    assert member_repository.get_member_scoped("0977777777", LEGACY_DEFAULT_SCOPE) is None
    assert recommendation_event_repository.get_recommendation_events_scoped(LEGACY_DEFAULT_SCOPE, "legacy-session")
    assert recommendation_event_repository.get_recommendation_events_scoped(tenant_b_scope, "legacy-session") == []

    member_session_repository.bind_session_scoped("tenant-b-session", "0987654321", tenant_b_scope)
    assert member_session_repository.get_session_phone_scoped("tenant-b-session", tenant_b_scope) == "0987654321"
    assert member_session_repository.get_session_phone_scoped("tenant-b-session", LEGACY_DEFAULT_SCOPE) == ""

    default_store_b_scope = type(LEGACY_DEFAULT_SCOPE)(
        LEGACY_DEFAULT_SCOPE.tenant_id,
        default_store_b,
        default_device_b,
    )
    default_device_c_scope = type(LEGACY_DEFAULT_SCOPE)(
        LEGACY_DEFAULT_SCOPE.tenant_id,
        LEGACY_DEFAULT_SCOPE.store_id,
        default_device_c,
    )
    audit_record = {
        "audit_id": "shared-audit",
        "actor": "store-a",
        "action": "original",
        "target_type": "promotion",
        "target_id": "promo-a",
        "metadata": {"source": "store-a"},
        "created_at": "2026-07-13T00:00:00",
    }
    admin_audit_repository.append_admin_audit_scoped(audit_record, LEGACY_DEFAULT_SCOPE)
    with pytest.raises(admin_audit_repository.CommercialScopeConflictError):
        admin_audit_repository.append_admin_audit_scoped(
            {**audit_record, "actor": "store-b", "action": "overwrite"},
            default_store_b_scope,
        )
    tenant_audit = {**audit_record, "audit_id": "tenant-audit", "store_id": None, "action": "tenant-original"}
    admin_audit_repository.append_admin_audit_scoped(tenant_audit, LEGACY_DEFAULT_SCOPE)
    admin_audit_repository.append_admin_audit_scoped(
        {**tenant_audit, "action": "tenant-updated"},
        LEGACY_DEFAULT_SCOPE,
    )

    member_session_repository.bind_session_scoped("shared-session", "0912345678", LEGACY_DEFAULT_SCOPE)
    with pytest.raises(member_session_repository.CommercialScopeConflictError):
        member_session_repository.bind_session_scoped("shared-session", "0912345678", default_device_c_scope)
    with pytest.raises(member_session_repository.CommercialScopeConflictError):
        member_session_repository.bind_session_scoped("shared-session", "0912345678", default_store_b_scope)

    recommendation_event_repository.append_recommendation_event_scoped(
        {
            "event_id": "tenant-b-event",
            "session_id": "shared-session-id",
            "event_type": "recommendation_shown",
        },
        tenant_b_scope,
    )
    assert len(recommendation_event_repository.get_recommendation_events_scoped(tenant_b_scope)) == 1
    assert (
        recommendation_event_repository.get_recommendation_events_scoped(LEGACY_DEFAULT_SCOPE, "shared-session-id")
        == []
    )
    with pytest.raises(recommendation_event_repository.CommercialScopeConflictError):
        recommendation_event_repository.append_recommendation_event_scoped(
            {"event_id": "legacy-event", "session_id": "cross-tenant"},
            tenant_b_scope,
        )
    recommendation_event_repository.append_recommendation_event_scoped(
        {
            "event_id": "shared-event",
            "session_id": "device-a-session",
            "event_type": "recommendation_shown",
            "metadata": {"device": "a"},
            "timestamp": "2026-07-13T00:00:00",
        },
        LEGACY_DEFAULT_SCOPE,
    )
    with pytest.raises(recommendation_event_repository.CommercialScopeConflictError):
        recommendation_event_repository.append_recommendation_event_scoped(
            {"event_id": "shared-event", "session_id": "device-b-session", "event_type": "overwritten"},
            default_device_c_scope,
        )

    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        scoped_session = conn.execute("SELECT * FROM member_sessions WHERE session_id = 'tenant-b-session'").fetchone()
        scoped_event = conn.execute("SELECT * FROM recommendation_events WHERE event_id = 'tenant-b-event'").fetchone()
        scoped_order = conn.execute("SELECT * FROM member_orders WHERE phone = '0977777777'").fetchone()
        audit = conn.execute("SELECT * FROM admin_audit_logs WHERE audit_id = 'shared-audit'").fetchone()
        tenant_audit_row = conn.execute("SELECT * FROM admin_audit_logs WHERE audit_id = 'tenant-audit'").fetchone()
        shared_session = conn.execute("SELECT * FROM member_sessions WHERE session_id = 'shared-session'").fetchone()
        shared_event = conn.execute("SELECT * FROM recommendation_events WHERE event_id = 'shared-event'").fetchone()
        assert scoped_session["origin_device_id"] == device_b
        assert scoped_event["device_id"] == device_b
        assert scoped_order["tenant_id"] == tenant_b
        assert scoped_order["store_id"] == store_b
        assert scoped_order["origin_device_id"] == device_b
        assert audit["actor"] == "store-a"
        assert audit["action"] == "original"
        assert audit["target_id"] == "promo-a"
        assert audit["metadata"] == {"source": "store-a"}
        assert audit["created_at"] == "2026-07-13T00:00:00"
        assert tenant_audit_row["store_id"] is None
        assert tenant_audit_row["action"] == "tenant-updated"
        assert shared_session["origin_device_id"] == LEGACY_DEFAULT_SCOPE.device_id
        assert shared_event["device_id"] == LEGACY_DEFAULT_SCOPE.device_id
        assert shared_event["session_id"] == "device-a-session"
        assert shared_event["event_type"] == "recommendation_shown"
        assert shared_event["metadata"] == {"device": "a"}
