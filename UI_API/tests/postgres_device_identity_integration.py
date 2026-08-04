"""CI-only PostgreSQL integration for Milestone 1D Device identity."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_device_identity_issue_rotation_revocation_and_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg
    from psycopg.rows import dict_row

    from models.admin_identity import AdminPrincipal
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE, CommercialScope
    from repositories import postgres_utils
    from services import device_identity_service

    base_url = postgres_utils.database_url()
    schema = "device_identity_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)
    postgres_utils.init_schema()

    admin = AdminPrincipal(
        user_id=uuid4(),
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        allowed_store_ids=(LEGACY_DEFAULT_SCOPE.store_id,),
        roles=("device-manager",),
        permissions=("device_identity.manage",),
        session_id=uuid4(),
        auth_method="session",
    )
    scope = CommercialScope(LEGACY_DEFAULT_SCOPE.tenant_id, LEGACY_DEFAULT_SCOPE.store_id)
    issued = device_identity_service.issue_device_credential(admin, scope, LEGACY_DEFAULT_SCOPE.device_id)

    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        stored = conn.execute(
            "SELECT credential_hash FROM device_credentials WHERE id = %s", (issued.credential_id,)
        ).fetchone()
        assert stored["credential_hash"] == device_identity_service.hash_device_secret(issued.credential)
        assert issued.credential not in stored["credential_hash"]

    session = device_identity_service.create_device_session(
        issued.key_id,
        issued.credential,
        untrusted_headers={
            "X-Tenant-ID": str(uuid4()),
            "X-Store-ID": str(uuid4()),
            "X-Device-ID": str(uuid4()),
        },
    )
    authenticated = device_identity_service.authenticate_device_session(session.token)
    assert authenticated is not None
    assert authenticated.device_id == LEGACY_DEFAULT_SCOPE.device_id
    assert authenticated.store_id == LEGACY_DEFAULT_SCOPE.store_id
    assert authenticated.tenant_id == LEGACY_DEFAULT_SCOPE.tenant_id

    rotated = device_identity_service.rotate_device_credential(admin, scope, issued.credential_id)
    old_during_overlap = device_identity_service.create_device_session(issued.key_id, issued.credential)
    assert old_during_overlap.principal.credential_id == issued.credential_id
    new_session = device_identity_service.create_device_session(rotated.key_id, rotated.credential)
    assert new_session.principal.credential_id == rotated.credential_id

    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        old = conn.execute(
            "SELECT rotation_valid_until FROM device_credentials WHERE id = %s", (issued.credential_id,)
        ).fetchone()
        assert old["rotation_valid_until"] is not None
    with pytest.raises(device_identity_service.DeviceAuthenticationError):
        device_identity_service.create_device_session(
            issued.key_id,
            issued.credential,
            now=old["rotation_valid_until"] + timedelta(seconds=1),
        )

    assert device_identity_service.revoke_device_credential(admin, scope, rotated.credential_id) is True
    assert device_identity_service.authenticate_device_session(new_session.token) is None

    tenant_b = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    store_b = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    device_b = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        conn.execute(
            "INSERT INTO tenants (id, code, name, status) VALUES (%s, 'device-b', 'Device B', 'active')",
            (tenant_b,),
        )
        conn.execute(
            """
            INSERT INTO stores (id, tenant_id, code, name, timezone, status)
            VALUES (%s, %s, 'device-b', 'Device B', 'Asia/Taipei', 'active')
            """,
            (store_b, tenant_b),
        )
        conn.execute(
            """
            INSERT INTO devices (id, tenant_id, store_id, code, name, status)
            VALUES (%s, %s, %s, 'device-b', 'Device B', 'active')
            """,
            (device_b, tenant_b, store_b),
        )
        conn.commit()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO device_credentials (
                        id, tenant_id, store_id, device_id, key_id, credential_hash,
                        issued_at, expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW() + INTERVAL '1 day')
                    """,
                    (uuid4(), tenant_b, store_b, LEGACY_DEFAULT_SCOPE.device_id, "bad-scope", "bad-hash"),
                )
        event_rows = conn.execute(
            "SELECT event_type, metadata::text AS metadata FROM device_credential_events ORDER BY created_at"
        ).fetchall()
        assert {row["event_type"] for row in event_rows} >= {
            "device_credential_issued",
            "device_session_issued",
            "device_credential_rotated",
            "device_credential_revoked",
        }
        serialized_events = str(event_rows)
        assert issued.credential not in serialized_events
        assert rotated.credential not in serialized_events
        assert session.token not in serialized_events

    postgres_utils.init_schema()
    clean = postgres_utils.get_migration_plan()
    postgres_utils.validate_migration_plan(clean, require_clean=True)
