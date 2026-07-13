"""Milestone 1C admin identity, session, and RBAC contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
TENANT_ID = UUID("00000000-0000-4000-8000-000000000001")
STORE_ID = UUID("00000000-0000-4000-8000-000000000002")


def _principal(*, permissions: tuple[str, ...] = ("members.read",), stores: tuple[UUID, ...] = (STORE_ID,)):
    from models.admin_identity import AdminPrincipal

    return AdminPrincipal(
        user_id=uuid4(),
        tenant_id=TENANT_ID,
        allowed_store_ids=stores,
        roles=("operator",),
        permissions=permissions,
        session_id=uuid4(),
        auth_method="session",
    )


def test_admin_identity_migration_is_forward_only_and_scoped() -> None:
    migration = ROOT / "UI_API/backend/schemas/migrations/0003_admin_identity_rbac_foundation.sql"
    sql = migration.read_text(encoding="utf-8")

    for table in (
        "admin_users",
        "admin_roles",
        "admin_permissions",
        "admin_role_permissions",
        "admin_user_role_assignments",
        "admin_sessions",
    ):
        assert f"CREATE TABLE {table}" in sql
    assert "password_hash" in sql
    assert "token_hash" in sql
    assert "REFERENCES tenants" in sql
    assert "REFERENCES stores" in sql
    assert "0001_" not in migration.name and "0002_" not in migration.name


def test_password_hash_is_argon2id_and_supports_verify_and_rehash() -> None:
    from services.admin_identity_service import (
        admin_password_needs_rehash,
        hash_admin_password,
        verify_admin_password,
    )

    encoded = hash_admin_password("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert "correct horse battery staple" not in encoded
    assert verify_admin_password(encoded, "correct horse battery staple") is True
    assert verify_admin_password(encoded, "wrong") is False
    assert admin_password_needs_rehash(encoded) is False


def test_session_token_hash_is_deterministic_and_never_plaintext() -> None:
    from services.admin_identity_service import hash_admin_session_token

    token = "session-token-value"
    first = hash_admin_session_token(token)

    assert first == hash_admin_session_token(token)
    assert first != token
    assert len(first) == 64


def test_authorization_enforces_permission_tenant_and_store() -> None:
    from models.commercial_scope import CommercialScope
    from services.admin_authorization_service import AdminAuthorizationError, authorize_admin_action

    principal = _principal()
    scope = CommercialScope(TENANT_ID, STORE_ID)

    assert authorize_admin_action(principal, "members.read", scope) is principal
    with pytest.raises(AdminAuthorizationError, match="permission"):
        authorize_admin_action(principal, "members.write", scope)
    with pytest.raises(AdminAuthorizationError, match="tenant"):
        authorize_admin_action(principal, "members.read", CommercialScope(uuid4(), STORE_ID))
    with pytest.raises(AdminAuthorizationError, match="store"):
        authorize_admin_action(principal, "members.read", CommercialScope(TENANT_ID, uuid4()))


def test_login_uses_normalized_identity_and_stores_only_token_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    from models.commercial_scope import CommercialScope
    from services import admin_identity_service

    password_hash = admin_identity_service.hash_admin_password("valid-password")
    user_id = uuid4()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        admin_identity_service.admin_identity_repository,
        "find_admin_user",
        lambda tenant_id, login_identity: {
            "id": user_id,
            "tenant_id": tenant_id,
            "login_identity": login_identity,
            "password_hash": password_hash,
            "status": "active",
        },
    )
    monkeypatch.setattr(
        admin_identity_service.admin_identity_repository,
        "create_admin_session",
        lambda **values: captured.update(values) or {"id": values["session_id"]},
    )
    monkeypatch.setattr(
        admin_identity_service.admin_identity_repository,
        "load_admin_principal",
        lambda session_id, _now: {
            "user_id": user_id,
            "tenant_id": TENANT_ID,
            "allowed_store_ids": [STORE_ID],
            "roles": ["operator"],
            "permissions": ["members.read"],
            "session_id": session_id,
        },
    )
    monkeypatch.setattr(admin_identity_service, "_new_session_token", lambda: "raw-session-token")
    monkeypatch.setattr(admin_identity_service, "_record_auth_event", lambda *_args, **_kwargs: None)

    result = admin_identity_service.login_admin(
        "  Operator@Example.COM ",
        "valid-password",
        CommercialScope(TENANT_ID, STORE_ID),
    )

    assert result.token == "raw-session-token"
    assert captured["token_hash"] == admin_identity_service.hash_admin_session_token(result.token)
    assert "raw-session-token" not in str(captured)
    assert captured["tenant_id"] == TENANT_ID
    assert result.principal.tenant_id == TENANT_ID


@pytest.mark.parametrize("user_record", [None, {"status": "disabled", "password_hash": "unused"}])
def test_login_rejects_unknown_and_disabled_users_with_safe_error(
    monkeypatch: pytest.MonkeyPatch,
    user_record: dict[str, str] | None,
) -> None:
    from models.commercial_scope import CommercialScope
    from services import admin_identity_service

    monkeypatch.setattr(admin_identity_service.admin_identity_repository, "find_admin_user", lambda *_args: user_record)
    monkeypatch.setattr(admin_identity_service, "_record_auth_event", lambda *_args, **_kwargs: None)

    with pytest.raises(admin_identity_service.AdminAuthenticationError, match="Invalid credentials"):
        admin_identity_service.login_admin(
            "operator@example.com",
            "wrong-password",
            CommercialScope(TENANT_ID, STORE_ID),
        )


def test_session_expiry_and_revocation_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import admin_identity_service

    now = datetime.now(timezone.utc)
    base = {
        "user_id": uuid4(),
        "tenant_id": TENANT_ID,
        "allowed_store_ids": [STORE_ID],
        "roles": ["operator"],
        "permissions": ["members.read"],
        "session_id": uuid4(),
    }
    for row in (
        {**base, "expires_at": now - timedelta(seconds=1), "revoked_at": None},
        {**base, "expires_at": now + timedelta(hours=1), "revoked_at": now},
    ):
        monkeypatch.setattr(admin_identity_service.admin_identity_repository, "find_admin_session", lambda *_args: row)
        assert admin_identity_service.authenticate_admin_session("raw-token", now=now) is None


def test_admin_login_cookie_is_http_only_secure_and_not_returned_in_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from models.admin_identity import AdminSessionResult
    from routes import admin_identity_routes

    principal = _principal()
    monkeypatch.setattr(admin_identity_routes.config, "is_production", lambda: True)
    monkeypatch.setattr(admin_identity_routes, "resolve_commercial_scope", lambda *_args: None)
    monkeypatch.setattr(
        admin_identity_routes.admin_identity_service,
        "login_admin",
        lambda *_args, **_kwargs: AdminSessionResult(
            token="raw-cookie-token",
            principal=principal,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )

    app = FastAPI()
    app.include_router(admin_identity_routes.create_router({}))
    response = TestClient(app).post(
        "/api/admin/auth/login",
        json={"login_identity": "operator@example.com", "password": "valid-password"},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "raw-cookie-token" not in response.text


def test_legacy_admin_token_requires_explicit_compatibility_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException
    from starlette.requests import Request

    from utils import auth_utils

    monkeypatch.setattr(auth_utils.config, "is_security_enforced", lambda: True)
    monkeypatch.setattr(auth_utils.config, "is_demo_public_mode", lambda: False)
    monkeypatch.setattr(auth_utils.config, "get", lambda key, default=None: {
        "SECURITY_ENFORCED": True,
        "ENABLE_LEGACY_ADMIN_TOKEN": False,
        "ADMIN_API_TOKEN": "legacy-token",
    }.get(key, default))
    monkeypatch.setattr(auth_utils.admin_identity_service, "authenticate_admin_session", lambda _token: None)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"x-admin-token", b"legacy-token")]})

    with pytest.raises(HTTPException) as exc_info:
        auth_utils.require_admin_token(request)
    assert exc_info.value.status_code == 403

