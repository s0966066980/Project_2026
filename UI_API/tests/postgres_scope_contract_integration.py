"""PostgreSQL Milestone 1D -> 1E scope contract upgrade integration."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_milestone_1d_upgrades_to_complete_scoped_operational_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    from backend.scripts.validate_commercial_scope import collect_violations
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE, CommercialScope
    from repositories import (
        availability_repository,
        commercial_settings_repository,
        interaction_event_repository,
        postgres_utils,
        promotion_repository,
        rag_asset_scope_repository,
    )

    base_url = postgres_utils.database_url()
    schema = "scope_contract_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)

    migrations = postgres_utils.migration_files()
    monkeypatch.setattr(postgres_utils, "migration_files", lambda: migrations[:4])
    postgres_utils.init_schema()
    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        conn.execute(
            "INSERT INTO members (phone, nickname, tenant_id) VALUES (%s, %s, %s)",
            ("0912345678", "Preserved", LEGACY_DEFAULT_SCOPE.tenant_id),
        )
        conn.execute(
            """
            INSERT INTO member_sessions (
                session_id, phone, tenant_id, store_id, origin_device_id
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                "preserved-session",
                "0912345678",
                LEGACY_DEFAULT_SCOPE.tenant_id,
                LEGACY_DEFAULT_SCOPE.store_id,
                LEGACY_DEFAULT_SCOPE.device_id,
            ),
        )
        conn.commit()

    monkeypatch.setattr(postgres_utils, "migration_files", lambda: migrations)
    postgres_utils.init_schema()
    postgres_utils.validate_migration_plan(postgres_utils.get_migration_plan(), require_clean=True)

    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        preserved = conn.execute("SELECT nickname FROM members WHERE phone = '0912345678'").fetchone()
        assert preserved and preserved["nickname"] == "Preserved"
        with pytest.raises(psycopg.errors.NotNullViolation):
            with conn.transaction():
                conn.execute("INSERT INTO members (phone, nickname) VALUES ('0900000000', 'Bad')")

        tenant_b = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        store_b = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        device_b = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
        conn.execute(
            "INSERT INTO tenants (id, code, name, status) VALUES (%s, 'scope-b', 'Scope B', 'active')",
            (tenant_b,),
        )
        conn.execute(
            """
            INSERT INTO stores (id, tenant_id, code, name, timezone, status)
            VALUES (%s, %s, 'scope-b', 'Scope B', 'Asia/Taipei', 'active')
            """,
            (store_b, tenant_b),
        )
        conn.execute(
            """
            INSERT INTO devices (id, tenant_id, store_id, code, name, status)
            VALUES (%s, %s, %s, 'scope-b', 'Scope B', 'active')
            """,
            (device_b, tenant_b, store_b),
        )
        conn.commit()

    scope_b = CommercialScope(tenant_b, store_b, device_b)
    availability_repository.save_availability_scoped({"sold_out_item_ids": ["scope-a"]}, LEGACY_DEFAULT_SCOPE)
    availability_repository.save_availability_scoped({"sold_out_item_ids": ["scope-b"]}, scope_b)
    assert availability_repository.get_availability_scoped(LEGACY_DEFAULT_SCOPE)["sold_out_item_ids"] == ["scope-a"]
    assert availability_repository.get_availability_scoped(scope_b)["sold_out_item_ids"] == ["scope-b"]

    commercial_settings_repository.save_settings_scoped({"theme": "a"}, LEGACY_DEFAULT_SCOPE)
    commercial_settings_repository.save_settings_scoped({"theme": "b"}, scope_b)
    assert commercial_settings_repository.get_settings_scoped(LEGACY_DEFAULT_SCOPE)["theme"] == "a"
    assert commercial_settings_repository.get_settings_scoped(scope_b)["theme"] == "b"

    promotion_repository.save_promotion_scoped("shared-promotion", {"title": "A"}, LEGACY_DEFAULT_SCOPE)
    promotion_repository.save_promotion_scoped("shared-promotion", {"title": "B"}, scope_b)
    assert promotion_repository.list_promotions_scoped(LEGACY_DEFAULT_SCOPE) == [{"title": "A"}]
    assert promotion_repository.list_promotions_scoped(scope_b) == [{"title": "B"}]

    interaction_event_repository.append_interaction_event_scoped(
        {"event_id": "shared-event", "session_id": "session-a", "event_type": "touch"},
        LEGACY_DEFAULT_SCOPE,
    )
    interaction_event_repository.append_interaction_event_scoped(
        {"event_id": "shared-event", "session_id": "session-b", "event_type": "touch"},
        scope_b,
    )
    assert len(interaction_event_repository.get_interaction_events_scoped(LEGACY_DEFAULT_SCOPE, "session-a")) == 1
    assert interaction_event_repository.get_interaction_events_scoped(scope_b, "session-a") == []

    rag_asset_scope_repository.save_asset_scope("shared-asset", {"kind": "menu"}, scope_b)
    assert rag_asset_scope_repository.list_asset_scopes(LEGACY_DEFAULT_SCOPE) == []
    assert rag_asset_scope_repository.list_asset_scopes(scope_b) == [
        {"asset_id": "shared-asset", "metadata": {"kind": "menu"}}
    ]

    assert collect_violations() == []
    postgres_utils.init_schema()
    postgres_utils.validate_migration_plan(postgres_utils.get_migration_plan(), require_clean=True)
