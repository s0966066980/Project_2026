"""Per-device credential and short-lived session application service."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import config
from models.admin_identity import AdminPrincipal
from models.commercial_scope import CommercialScope
from models.device_identity import DeviceCredentialIssue, DevicePrincipal, DeviceSessionResult
from modules.identity._admin_authorization_service import authorize_admin_action
from modules.identity.adapters import device_identity as device_identity_repository
from repositories import postgres_utils


class DeviceAuthenticationError(ValueError):
    pass


def hash_device_secret(secret: str) -> str:
    return hashlib.sha256(str(secret).encode("utf-8")).hexdigest()


def _new_device_token() -> str:
    return secrets.token_urlsafe(48)


def _new_device_credential() -> str:
    return secrets.token_urlsafe(48)


def _record_device_event(event_type: str, record: Mapping[str, object], *, reason: str = "") -> None:
    device_identity_repository.record_device_event(
        event_id=uuid4(),
        tenant_id=record["tenant_id"],
        store_id=record["store_id"],
        device_id=record["device_id"],
        credential_id=record.get("credential_id"),
        event_type=event_type,
        metadata={"reason": reason} if reason else {},
        created_at=datetime.now(timezone.utc),
    )


def create_device_session(
    key_id: str,
    credential: str,
    *,
    untrusted_headers: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> DeviceSessionResult:
    del untrusted_headers
    resolved_now = now or datetime.now(timezone.utc)
    row = device_identity_repository.find_device_credential(str(key_id).strip())
    invalid = (
        row is None
        or str(row.get("status")) != "active"
        or row.get("revoked_at") is not None
        or str(row.get("device_status")) != "active"
        or not isinstance(row.get("expires_at"), datetime)
        or row["expires_at"] <= resolved_now
        or (isinstance(row.get("rotation_valid_until"), datetime) and row["rotation_valid_until"] <= resolved_now)
        or not secrets.compare_digest(str(row.get("credential_hash") or ""), hash_device_secret(credential))
    )
    if invalid:
        if row is not None:
            _record_device_event("device_auth_failure", row, reason="invalid_credential")
        raise DeviceAuthenticationError("Invalid device credential")
    assert row is not None

    session_id = uuid4()
    token = _new_device_token()
    expires_at = resolved_now + timedelta(seconds=max(60, int(config.get("DEVICE_SESSION_TTL_SEC", 3600) or 3600)))
    device_identity_repository.create_device_session(
        session_id=session_id,
        tenant_id=row["tenant_id"],
        store_id=row["store_id"],
        device_id=row["device_id"],
        credential_id=row["credential_id"],
        token_hash=hash_device_secret(token),
        issued_at=resolved_now,
        expires_at=expires_at,
    )
    principal = DevicePrincipal(
        device_id=UUID(str(row["device_id"])),
        store_id=UUID(str(row["store_id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        credential_id=UUID(str(row["credential_id"])),
        session_id=session_id,
        issued_at=resolved_now,
        expires_at=expires_at,
        auth_method="device_session",
    )
    _record_device_event("device_session_issued", row)
    return DeviceSessionResult(token, principal)


def authenticate_device_session(token: str, *, now: datetime | None = None) -> DevicePrincipal | None:
    if not token or not postgres_utils.use_postgres():
        return None
    resolved_now = now or datetime.now(timezone.utc)
    row = device_identity_repository.find_device_session(hash_device_secret(token), resolved_now)
    if (
        row is None
        or row.get("revoked_at") is not None
        or row.get("credential_revoked_at") is not None
        or str(row.get("credential_status")) != "active"
        or str(row.get("device_status")) != "active"
        or not isinstance(row.get("expires_at"), datetime)
        or row["expires_at"] <= resolved_now
    ):
        return None
    return DevicePrincipal(
        device_id=UUID(str(row["device_id"])),
        store_id=UUID(str(row["store_id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        credential_id=UUID(str(row["credential_id"])),
        session_id=UUID(str(row["session_id"])),
        issued_at=row["issued_at"],
        expires_at=row["expires_at"],
        auth_method="device_session",
    )


def legacy_device_principal(scope, *, now: datetime | None = None) -> DevicePrincipal:
    resolved_now = now or datetime.now(timezone.utc)
    return DevicePrincipal(
        device_id=scope.device_id,
        store_id=scope.store_id,
        tenant_id=scope.tenant_id,
        credential_id=None,
        session_id=None,
        issued_at=resolved_now,
        expires_at=resolved_now + timedelta(minutes=5),
        auth_method="legacy_token",
    )


def record_legacy_device_use(scope) -> None:
    if not postgres_utils.use_postgres():
        return
    _record_device_event(
        "legacy_device_token_used",
        {
            "tenant_id": scope.tenant_id,
            "store_id": scope.store_id,
            "device_id": scope.device_id,
            "credential_id": None,
        },
        reason="deprecated_compatibility",
    )


def issue_device_credential(
    principal: AdminPrincipal,
    scope: CommercialScope,
    device_id: UUID,
    *,
    now: datetime | None = None,
) -> DeviceCredentialIssue:
    authorize_admin_action(principal, "device_identity.manage", scope)
    device = device_identity_repository.find_active_device(scope.tenant_id, scope.store_id, device_id)
    if device is None:
        raise ValueError("Device is not active in the authorized scope")
    resolved_now = now or datetime.now(timezone.utc)
    expires_at = resolved_now + timedelta(days=max(1, int(config.get("DEVICE_CREDENTIAL_TTL_DAYS", 90) or 90)))
    credential_id = uuid4()
    key_id = f"dev_{uuid4().hex}"
    raw_credential = _new_device_credential()
    record = device_identity_repository.create_device_credential(
        credential_id=credential_id,
        tenant_id=scope.tenant_id,
        store_id=scope.store_id,
        device_id=device_id,
        key_id=key_id,
        credential_hash=hash_device_secret(raw_credential),
        issued_at=resolved_now,
        expires_at=expires_at,
    )
    _record_device_event("device_credential_issued", record)
    return DeviceCredentialIssue(credential_id, key_id, raw_credential, expires_at)


def rotate_device_credential(
    principal: AdminPrincipal,
    scope: CommercialScope,
    credential_id: UUID,
    *,
    now: datetime | None = None,
) -> DeviceCredentialIssue:
    authorize_admin_action(principal, "device_identity.manage", scope)
    resolved_now = now or datetime.now(timezone.utc)
    expires_at = resolved_now + timedelta(days=max(1, int(config.get("DEVICE_CREDENTIAL_TTL_DAYS", 90) or 90)))
    grace_until = resolved_now + timedelta(
        seconds=max(0, int(config.get("DEVICE_CREDENTIAL_ROTATION_GRACE_SEC", 300) or 300))
    )
    replacement_id = uuid4()
    key_id = f"dev_{uuid4().hex}"
    raw_credential = _new_device_credential()
    replacement = device_identity_repository.rotate_device_credential(
        old_credential_id=credential_id,
        credential_id=replacement_id,
        tenant_id=scope.tenant_id,
        store_id=scope.store_id,
        key_id=key_id,
        credential_hash=hash_device_secret(raw_credential),
        issued_at=resolved_now,
        expires_at=expires_at,
        rotation_valid_until=grace_until,
    )
    if replacement is None:
        raise ValueError("Device credential is not active in the authorized scope")
    _record_device_event("device_credential_rotated", replacement)
    return DeviceCredentialIssue(replacement_id, key_id, raw_credential, expires_at)


def revoke_device_credential(
    principal: AdminPrincipal,
    scope: CommercialScope,
    credential_id: UUID,
    *,
    now: datetime | None = None,
) -> bool:
    authorize_admin_action(principal, "device_identity.manage", scope)
    record = device_identity_repository.find_scoped_device_credential(credential_id, scope.tenant_id, scope.store_id)
    if record is None:
        return False
    revoked = device_identity_repository.revoke_device_credential(credential_id, now or datetime.now(timezone.utc))
    if revoked:
        _record_device_event("device_credential_revoked", record)
    return revoked


def touch_device_principal(principal: DevicePrincipal, app_version: str) -> None:
    if principal.auth_method != "device_session":
        return
    safe_version = str(app_version or "").strip()[:64]
    device_identity_repository.touch_device(
        principal.device_id,
        app_version=safe_version,
        seen_at=datetime.now(timezone.utc),
    )
