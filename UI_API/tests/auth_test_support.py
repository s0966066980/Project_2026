"""Explicit durable-session principals for route and contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from models.admin_identity import AdminPrincipal
from models.admin_permissions import ADMIN_PERMISSION_NAMES
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from models.device_identity import DevicePrincipal

ADMIN_SESSION_TOKEN = "test-admin-session"
DEVICE_SESSION_TOKEN = "test-device-session"


def configure_admin_session(monkeypatch, *, permissions: tuple[str, ...] | None = None) -> AdminPrincipal:
    from services import admin_identity_service

    principal = AdminPrincipal(
        user_id=uuid4(),
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        allowed_store_ids=(LEGACY_DEFAULT_SCOPE.store_id,),
        roles=("test-manager",),
        permissions=permissions or tuple(sorted(ADMIN_PERMISSION_NAMES)),
        session_id=uuid4(),
        auth_method="session",
    )
    monkeypatch.setattr(
        admin_identity_service,
        "authenticate_admin_session",
        lambda token: principal if token == ADMIN_SESSION_TOKEN else None,
    )
    return principal


def configure_device_session(monkeypatch) -> DevicePrincipal:
    from services import device_identity_service

    now = datetime.now(timezone.utc)
    principal = DevicePrincipal(
        device_id=LEGACY_DEFAULT_SCOPE.device_id,
        store_id=LEGACY_DEFAULT_SCOPE.store_id,
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        credential_id=uuid4(),
        session_id=uuid4(),
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        auth_method="device_session",
    )
    monkeypatch.setattr(
        device_identity_service,
        "authenticate_device_session",
        lambda token: principal if token == DEVICE_SESSION_TOKEN else None,
    )
    monkeypatch.setattr(device_identity_service, "touch_device_principal", lambda *_args, **_kwargs: None)
    return principal


def authenticate_client(client, *, admin: bool = True, device: bool = False) -> None:
    if admin:
        client.cookies.set("admin_session", ADMIN_SESSION_TOKEN)
    if device:
        client.cookies.set("kiosk_device_session", DEVICE_SESSION_TOKEN)
