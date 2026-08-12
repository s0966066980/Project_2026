"""Dormant Admin identity persistence for future external integrations."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

import config
from models.admin_identity import AdminPrincipal, AdminSessionResult
from models.admin_permissions import ADMIN_PERMISSION_CATALOG
from models.commercial_scope import CommercialScope
from modules.identity.adapters import postgres as admin_identity_repository
from repositories import admin_audit_repository, postgres_utils

_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


class AdminAuthenticationError(ValueError):
    pass


def normalize_admin_login(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def hash_admin_password(password: str) -> str:
    if not str(password):
        raise ValueError("Admin password must not be empty")
    return _PASSWORD_HASHER.hash(password)


def verify_admin_password(encoded: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(encoded, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def admin_password_needs_rehash(encoded: str) -> bool:
    try:
        return _PASSWORD_HASHER.check_needs_rehash(encoded)
    except InvalidHashError:
        return True


def hash_admin_session_token(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _new_session_token() -> str:
    return secrets.token_urlsafe(48)


def _principal_from_record(record: dict, auth_method: str = "session") -> AdminPrincipal:
    return AdminPrincipal(
        user_id=UUID(str(record["user_id"])),
        tenant_id=UUID(str(record["tenant_id"])),
        allowed_store_ids=tuple(UUID(str(value)) for value in record.get("allowed_store_ids", [])),
        roles=tuple(str(value) for value in record.get("roles", [])),
        permissions=tuple(str(value) for value in record.get("permissions", [])),
        session_id=UUID(str(record["session_id"])) if record.get("session_id") else None,
        auth_method="legacy_token" if auth_method == "legacy_token" else "session",
    )


def _record_auth_event(action: str, scope: CommercialScope, *, user_id: object = "", reason: str = "") -> None:
    admin_audit_repository.append_admin_audit_scoped(
        {
            "audit_id": f"aud_{uuid4().hex}",
            "actor": str(user_id or "unknown-admin"),
            "action": action,
            "target_type": "admin_session",
            "target_id": str(user_id or "unknown"),
            "metadata": {"reason": reason} if reason else {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        scope,
    )


def login_admin(login_identity: str, password: str, scope: CommercialScope) -> AdminSessionResult:
    normalized = normalize_admin_login(login_identity)
    user = admin_identity_repository.find_admin_user(scope.tenant_id, normalized)
    if (
        user is None
        or str(user.get("status")) != "active"
        or not verify_admin_password(str(user.get("password_hash") or ""), password)
    ):
        _record_auth_event("admin_login_failure", scope, reason="invalid_credentials")
        raise AdminAuthenticationError("Invalid credentials")

    if admin_password_needs_rehash(str(user["password_hash"])):
        admin_identity_repository.update_admin_password_hash(
            UUID(str(user["id"])), scope.tenant_id, hash_admin_password(password)
        )

    now = datetime.now(timezone.utc)
    ttl_seconds = max(300, int(config.get("ADMIN_SESSION_TTL_SEC", 28800) or 28800))
    expires_at = now + timedelta(seconds=ttl_seconds)
    raw_token = _new_session_token()
    session_id = uuid4()
    admin_identity_repository.create_admin_session(
        session_id=session_id,
        tenant_id=scope.tenant_id,
        user_id=user["id"],
        token_hash=hash_admin_session_token(raw_token),
        issued_at=now,
        expires_at=expires_at,
    )
    principal_record = admin_identity_repository.load_admin_principal(session_id, now)
    if principal_record is None:
        raise AdminAuthenticationError("Admin session could not be established")
    principal = _principal_from_record(principal_record)
    _record_auth_event("admin_login_success", scope, user_id=principal.user_id)
    return AdminSessionResult(token=raw_token, principal=principal, expires_at=expires_at)


def authenticate_admin_session(token: str, *, now: datetime | None = None) -> AdminPrincipal | None:
    if not token:
        return None
    resolved_now = now or datetime.now(timezone.utc)
    if not postgres_utils.use_postgres():
        return None
    row = admin_identity_repository.find_admin_session(hash_admin_session_token(token))
    if row is None or row.get("revoked_at") is not None or str(row.get("user_status")) == "disabled":
        return None
    expires_at = row.get("expires_at")
    if not isinstance(expires_at, datetime) or expires_at <= resolved_now:
        return None
    principal = admin_identity_repository.load_admin_principal(UUID(str(row["session_id"])), resolved_now)
    return _principal_from_record(principal) if principal else None


def logout_admin(token: str, scope: CommercialScope) -> bool:
    if not token:
        return False
    if not postgres_utils.use_postgres():
        return False
    revoked = admin_identity_repository.revoke_admin_session(
        hash_admin_session_token(token), datetime.now(timezone.utc)
    )
    if revoked:
        _record_auth_event("admin_logout", scope)
    return revoked


def rotate_admin_session(token: str, scope: CommercialScope) -> AdminSessionResult:
    principal = authenticate_admin_session(token)
    if principal is None or principal.tenant_id != scope.tenant_id or scope.store_id not in principal.allowed_store_ids:
        raise AdminAuthenticationError("Admin session is not valid")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=max(300, int(config.get("ADMIN_SESSION_TTL_SEC", 28800) or 28800)))
    raw_token = _new_session_token()
    session_id = uuid4()
    replaced = admin_identity_repository.rotate_admin_session(
        old_token_hash=hash_admin_session_token(token),
        new_session_id=session_id,
        new_token_hash=hash_admin_session_token(raw_token),
        issued_at=now,
        expires_at=expires_at,
    )
    if replaced is None:
        raise AdminAuthenticationError("Admin session is not valid")
    principal_record = admin_identity_repository.load_admin_principal(session_id, now)
    if principal_record is None:
        raise AdminAuthenticationError("Admin session could not be rotated")
    rotated_principal = _principal_from_record(principal_record)
    _record_auth_event("admin_session_rotated", scope, user_id=rotated_principal.user_id)
    return AdminSessionResult(token=raw_token, principal=rotated_principal, expires_at=expires_at)


def sync_admin_permission_catalog() -> dict[str, UUID]:
    """Idempotently synchronize stable machine names during trusted provisioning."""

    resolved: dict[str, UUID] = {}
    for machine_name, description in ADMIN_PERMISSION_CATALOG:
        row = admin_identity_repository.upsert_admin_permission(uuid4(), machine_name, description)
        resolved[machine_name] = UUID(str(row["id"]))
    return resolved
