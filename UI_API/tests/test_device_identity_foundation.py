"""Milestone 1D per-device identity security contracts."""

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
DEVICE_ID = UUID("00000000-0000-4000-8000-000000000003")


def test_device_identity_migration_is_scoped_and_forward_only() -> None:
    migration = ROOT / "UI_API/backend/schemas/migrations/0004_device_identity_foundation.sql"
    sql = migration.read_text(encoding="utf-8")

    for table in ("device_credentials", "device_sessions", "device_credential_events"):
        assert f"CREATE TABLE {table}" in sql
    assert "credential_hash" in sql
    assert "token_hash" in sql
    assert "REFERENCES devices" in sql
    assert "key_id" in sql


def test_device_principal_is_typed_and_scope_is_immutable() -> None:
    from models.device_identity import DevicePrincipal

    principal = DevicePrincipal(
        device_id=DEVICE_ID,
        store_id=STORE_ID,
        tenant_id=TENANT_ID,
        credential_id=uuid4(),
        session_id=uuid4(),
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        auth_method="device_session",
    )

    assert principal.device_id == DEVICE_ID
    with pytest.raises(AttributeError):
        principal.device_id = uuid4()  # type: ignore[misc]


def test_device_credential_and_session_hashes_never_contain_raw_secret() -> None:
    from services.device_identity_service import hash_device_secret

    raw = "device-secret-value"
    encoded = hash_device_secret(raw)

    assert encoded == hash_device_secret(raw)
    assert encoded != raw
    assert raw not in encoded
    assert len(encoded) == 64


def test_device_session_uses_database_owned_scope_not_client_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import device_identity_service

    credential_id = uuid4()
    monkeypatch.setattr(
        device_identity_service.device_identity_repository,
        "find_device_credential",
        lambda _key_id: {
            "credential_id": credential_id,
            "tenant_id": TENANT_ID,
            "store_id": STORE_ID,
            "device_id": DEVICE_ID,
            "credential_hash": device_identity_service.hash_device_secret("valid-device-secret"),
            "status": "active",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "revoked_at": None,
            "device_status": "active",
        },
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        device_identity_service.device_identity_repository,
        "create_device_session",
        lambda **values: captured.update(values) or values,
    )
    monkeypatch.setattr(device_identity_service, "_new_device_token", lambda: "raw-device-session")
    monkeypatch.setattr(device_identity_service, "_record_device_event", lambda *_args, **_kwargs: None)

    result = device_identity_service.create_device_session(
        "device-key",
        "valid-device-secret",
        untrusted_headers={"X-Tenant-ID": str(uuid4()), "X-Store-ID": str(uuid4())},
    )

    assert result.principal.tenant_id == TENANT_ID
    assert result.principal.store_id == STORE_ID
    assert result.principal.device_id == DEVICE_ID
    assert captured["token_hash"] == device_identity_service.hash_device_secret(result.token)
    assert result.token not in str(captured)


@pytest.mark.parametrize("state", ["revoked", "expired", "disabled"])
def test_revoked_expired_or_disabled_credential_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    from services import device_identity_service

    now = datetime.now(timezone.utc)
    row = {
        "credential_id": uuid4(),
        "tenant_id": TENANT_ID,
        "store_id": STORE_ID,
        "device_id": DEVICE_ID,
        "credential_hash": device_identity_service.hash_device_secret("valid-device-secret"),
        "status": "active",
        "expires_at": now + timedelta(days=1),
        "revoked_at": None,
        "device_status": "active",
    }
    if state == "revoked":
        row["revoked_at"] = now
    elif state == "expired":
        row["expires_at"] = now - timedelta(seconds=1)
    else:
        row["device_status"] = "disabled"
    monkeypatch.setattr(device_identity_service.device_identity_repository, "find_device_credential", lambda _key: row)
    monkeypatch.setattr(device_identity_service, "_record_device_event", lambda *_args, **_kwargs: None)

    with pytest.raises(device_identity_service.DeviceAuthenticationError, match="Invalid device credential"):
        device_identity_service.create_device_session("device-key", "valid-device-secret", now=now)


def test_device_session_cookie_is_http_only_secure_and_not_in_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from models.device_identity import DevicePrincipal, DeviceSessionResult
    from routes import device_identity_routes

    now = datetime.now(timezone.utc)
    principal = DevicePrincipal(
        device_id=DEVICE_ID,
        store_id=STORE_ID,
        tenant_id=TENANT_ID,
        credential_id=uuid4(),
        session_id=uuid4(),
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        auth_method="device_session",
    )
    monkeypatch.setattr(device_identity_routes.config, "is_production", lambda: True)
    monkeypatch.setattr(
        device_identity_routes.device_identity_service,
        "create_device_session",
        lambda *_args, **_kwargs: DeviceSessionResult("raw-device-session", principal),
    )
    app = FastAPI()
    app.include_router(device_identity_routes.create_router({}))

    response = TestClient(app).post(
        "/api/device/auth/session",
        json={"key_id": "device-key", "credential": "one-time-secret"},
    )

    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "raw-device-session" not in response.text


def test_legacy_kiosk_token_requires_explicit_compatibility_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException
    from starlette.requests import Request

    from utils import auth_utils

    monkeypatch.setattr(auth_utils.config, "is_security_enforced", lambda: True)
    monkeypatch.setattr(auth_utils.config, "is_demo_public_mode", lambda: False)
    monkeypatch.setattr(
        auth_utils.config,
        "get",
        lambda key, default=None: {
            "SECURITY_ENFORCED": True,
            "ENABLE_LEGACY_KIOSK_TOKEN": False,
            "KIOSK_DEVICE_TOKEN": "legacy-kiosk-token",
        }.get(key, default),
    )
    monkeypatch.setattr(auth_utils.device_identity_service, "authenticate_device_session", lambda _token: None)
    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [(b"x-kiosk-token", b"legacy-kiosk-token")]}
    )

    with pytest.raises(HTTPException) as exc_info:
        auth_utils.require_kiosk_token(request)
    assert exc_info.value.status_code == 403
