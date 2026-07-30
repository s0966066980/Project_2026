"""PostgreSQL integration for Member UUID, PII protection, and key rotation."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_legacy_members_upgrade_to_uuid_protected_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    from backend.scripts.verify_member_identity_migration import (
        backfill_member_identity,
        collect_violations,
    )
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE, CommercialScope
    from repositories import member_repository, postgres_utils
    from services.member_key_provider import DevelopmentMemberKeyProvider
    from services.member_pii_service import protect_phone, reveal_phone

    base_url = postgres_utils.database_url()
    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("ALLOW_POSTGRES_JSON_FALLBACK", "false")
    monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "postgresql")
    schema = "member_identity_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)

    migrations = postgres_utils.migration_files()
    monkeypatch.setattr(postgres_utils, "migration_files", lambda: migrations[:5])
    postgres_utils.init_schema()
    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        conn.execute(
            "INSERT INTO members (phone, nickname, tenant_id) VALUES (%s, %s, %s)",
            ("0912345678", "Legacy", LEGACY_DEFAULT_SCOPE.tenant_id),
        )
        conn.execute("INSERT INTO member_preferences (phone) VALUES ('0912345678')")
        conn.execute(
            """
            INSERT INTO member_sessions (
                session_id, phone, tenant_id, store_id, origin_device_id
            ) VALUES ('legacy-session', '0912345678', %s, %s, %s)
            """,
            (
                LEGACY_DEFAULT_SCOPE.tenant_id,
                LEGACY_DEFAULT_SCOPE.store_id,
                LEGACY_DEFAULT_SCOPE.device_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO member_orders (phone, tenant_id, store_id, origin_device_id, session_id)
            VALUES ('0912345678', %s, %s, %s, 'legacy-session')
            """,
            (
                LEGACY_DEFAULT_SCOPE.tenant_id,
                LEGACY_DEFAULT_SCOPE.store_id,
                LEGACY_DEFAULT_SCOPE.device_id,
            ),
        )
        conn.commit()

    monkeypatch.setattr(postgres_utils, "migration_files", lambda: migrations)
    postgres_utils.init_schema()
    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        member = conn.execute(
            "SELECT id, phone FROM members WHERE tenant_id = %s",
            (LEGACY_DEFAULT_SCOPE.tenant_id,),
        ).fetchone()
        assert member and member["id"] is not None and member["phone"] == "0912345678"
        for table in ("member_preferences", "member_sessions", "member_orders"):
            reference = conn.execute(f"SELECT member_id FROM {table} LIMIT 1").fetchone()
            assert reference and reference["member_id"] == member["id"]

    v1 = DevelopmentMemberKeyProvider("v1")
    assert backfill_member_identity(v1) == 1
    assert backfill_member_identity(v1) == 0
    assert collect_violations(v1) == []

    tenant_b = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    store_b = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    device_b = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    with psycopg.connect(scoped_url) as conn:
        conn.execute(
            "INSERT INTO tenants (id, code, name, status) VALUES (%s, 'member-b', 'Member B', 'active')",
            (tenant_b,),
        )
        conn.execute(
            """
            INSERT INTO stores (id, tenant_id, code, name, timezone, status)
            VALUES (%s, %s, 'member-b', 'Member B', 'Asia/Taipei', 'active')
            """,
            (store_b, tenant_b),
        )
        conn.execute(
            """
            INSERT INTO devices (id, tenant_id, store_id, code, name, status)
            VALUES (%s, %s, %s, 'member-b', 'Member B', 'active')
            """,
            (device_b, tenant_b, store_b),
        )
        conn.commit()

    scope_b = CommercialScope(tenant_b, store_b, device_b)
    protected_b = protect_phone("0912345678", tenant_b, v1)
    stored_b = member_repository.upsert_member_scoped(
        {
            "phone": "0912345678",
            "nickname": "Tenant B",
            "phone_lookup_hash": protected_b.phone_lookup_hash,
            "phone_encrypted": protected_b.phone_encrypted,
            "phone_masked": protected_b.phone_masked,
            "key_version": protected_b.key_version,
        },
        scope_b,
    )
    assert member_repository.get_member_by_id_scoped(UUID(stored_b["member_id"]), scope_b)["nickname"] == "Tenant B"
    assert (
        member_repository.get_member_by_lookup_hash_scoped(protected_b.phone_lookup_hash, scope_b)["nickname"]
        == "Tenant B"
    )
    assert (
        member_repository.get_member_by_lookup_hash_scoped(protected_b.phone_lookup_hash, LEGACY_DEFAULT_SCOPE) is None
    )

    member_repository.upsert_member_scoped({**stored_b, "nickname": "Tenant B Updated"}, scope_b)
    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT id, phone, phone_encrypted, key_version FROM members WHERE phone = '0912345678'"
        ).fetchall()
        assert len(rows) == 2
        assert all(row["phone"] not in row["phone_encrypted"] for row in rows)

    v2 = DevelopmentMemberKeyProvider("v2")
    assert backfill_member_identity(v2) == 2
    assert collect_violations(v2) == []
    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        rows = conn.execute("SELECT phone_encrypted, key_version FROM members ORDER BY id").fetchall()
        assert {row["key_version"] for row in rows} == {"v2"}
        assert all(reveal_phone(row["phone_encrypted"], "v2", v2) == "0912345678" for row in rows)

    assert member_repository.anonymize_member_by_id_scoped(UUID(stored_b["member_id"]), scope_b)
    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        deleted = conn.execute(
            """SELECT phone, phone_lookup_hash, phone_encrypted, phone_masked,
                      key_version, anonymized_at, deleted_at
               FROM members WHERE id = %s""",
            (UUID(stored_b["member_id"]),),
        ).fetchone()
        assert deleted
        assert deleted["phone"].startswith("deleted:")
        assert deleted["phone_lookup_hash"] is None
        assert deleted["phone_encrypted"] is None
        assert deleted["phone_masked"] == "deleted"
        assert deleted["key_version"] is None
        assert deleted["anonymized_at"] is not None
        assert deleted["deleted_at"]
        assert (
            conn.execute(
                "SELECT COUNT(*) AS count FROM member_preferences WHERE member_id = %s",
                (UUID(stored_b["member_id"]),),
            ).fetchone()["count"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) AS count FROM members WHERE tenant_id = %s AND phone = '0912345678'",
                (LEGACY_DEFAULT_SCOPE.tenant_id,),
            ).fetchone()["count"]
            == 1
        )
    assert collect_violations(v2) == []
    assert backfill_member_identity(v2) == 0

    postgres_utils.init_schema()
    postgres_utils.validate_migration_plan(postgres_utils.get_migration_plan(), require_clean=True)
