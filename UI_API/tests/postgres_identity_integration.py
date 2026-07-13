"""CI-only PostgreSQL integration for Milestone 1C Admin identity and RBAC."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_admin_identity_upgrade_rbac_isolation_and_revocation(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg
    from psycopg.rows import dict_row

    from models.commercial_scope import LEGACY_DEFAULT_SCOPE, CommercialScope
    from repositories import admin_identity_repository, postgres_utils
    from services import admin_identity_service

    base_url = postgres_utils.database_url()
    schema = "admin_identity_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)

    postgres_utils.init_schema()
    plan = postgres_utils.get_migration_plan()
    assert plan.pending_versions == ()
    assert "0003_admin_identity_rbac_foundation" in plan.applied_versions

    user_id = uuid4()
    role_id = uuid4()
    password = "correct horse battery staple"
    admin_identity_repository.create_admin_user(
        user_id=user_id,
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        login_identity="operator@example.com",
        display_name="Operator",
        password_hash=admin_identity_service.hash_admin_password(password),
    )
    permissions = admin_identity_service.sync_admin_permission_catalog()
    admin_identity_repository.create_admin_role(
        role_id=role_id,
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        code="operator",
        name="Operator",
    )
    admin_identity_repository.grant_permission_to_role(
        LEGACY_DEFAULT_SCOPE.tenant_id, role_id, permissions["members.read"]
    )
    admin_identity_repository.assign_admin_role(
        assignment_id=uuid4(),
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        user_id=user_id,
        role_id=role_id,
        store_id=LEGACY_DEFAULT_SCOPE.store_id,
    )

    result = admin_identity_service.login_admin(
        "OPERATOR@EXAMPLE.COM",
        password,
        CommercialScope(LEGACY_DEFAULT_SCOPE.tenant_id, LEGACY_DEFAULT_SCOPE.store_id),
    )
    authenticated = admin_identity_service.authenticate_admin_session(result.token)
    assert authenticated is not None
    assert authenticated.user_id == user_id
    assert authenticated.permissions == ("members.read",)
    assert authenticated.allowed_store_ids == (LEGACY_DEFAULT_SCOPE.store_id,)

    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        stored_user = conn.execute("SELECT password_hash FROM admin_users WHERE id = %s", (user_id,)).fetchone()
        stored_session = conn.execute(
            "SELECT token_hash FROM admin_sessions WHERE id = %s", (result.principal.session_id,)
        ).fetchone()
        assert stored_user["password_hash"].startswith("$argon2id$")
        assert password not in stored_user["password_hash"]
        assert stored_session["token_hash"] == admin_identity_service.hash_admin_session_token(result.token)
        assert result.token not in stored_session["token_hash"]
        assert (
            conn.execute(
                "SELECT COUNT(*) AS count FROM admin_audit_logs WHERE action = 'admin_login_success'"
            ).fetchone()["count"]
            == 1
        )

        tenant_b = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        store_b = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        role_b = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
        conn.execute(
            "INSERT INTO tenants (id, code, name, status) VALUES (%s, %s, %s, 'active')",
            (tenant_b, "identity-b", "Identity B"),
        )
        conn.execute(
            "INSERT INTO stores (id, tenant_id, code, name, timezone, status) VALUES (%s, %s, %s, %s, %s, 'active')",
            (store_b, tenant_b, "identity-b", "Identity B", "Asia/Taipei"),
        )
        conn.execute(
            "INSERT INTO admin_roles (id, tenant_id, code, name) VALUES (%s, %s, %s, %s)",
            (role_b, tenant_b, "operator", "Operator B"),
        )
        conn.commit()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO admin_user_role_assignments
                        (id, tenant_id, user_id, role_id, store_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (uuid4(), tenant_b, user_id, role_b, store_b),
                )

    assert (
        admin_identity_repository.find_admin_user(UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"), "operator@example.com")
        is None
    )
    rotated = admin_identity_service.rotate_admin_session(result.token, LEGACY_DEFAULT_SCOPE)
    assert admin_identity_service.authenticate_admin_session(result.token) is None
    assert admin_identity_service.authenticate_admin_session(rotated.token) is not None
    assert admin_identity_service.logout_admin(rotated.token, LEGACY_DEFAULT_SCOPE) is True
    assert admin_identity_service.authenticate_admin_session(rotated.token) is None

    postgres_utils.init_schema()
    clean = postgres_utils.get_migration_plan()
    postgres_utils.validate_migration_plan(clean, require_clean=True)
