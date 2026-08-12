"""Public Application API for the identity module."""

from __future__ import annotations

# Temporary re-export of internal implementation for tests mid-cutover.
from modules.identity import _admin_identity_service as admin_identity_service

# Device credentials, fleet commands and scope resolution moved in from
# services/ with the capability. They are re-exported as modules so existing
# call sites keep their `device_identity_service.x` shape.
from modules.identity import _device_identity_service as device_identity_service  # noqa: E402
from modules.identity import _fleet_management_service as fleet_management_service  # noqa: E402
from modules.identity._admin_authorization_service import (
    AdminAuthorizationError,
    authorize_admin_action,
)
from modules.identity._admin_identity_service import (
    AdminAuthenticationError,
    admin_password_needs_rehash,
    authenticate_admin_session,
    hash_admin_password,
    hash_admin_session_token,
    login_admin,
    logout_admin,
    normalize_admin_login,
    rotate_admin_session,
    sync_admin_permission_catalog,
    verify_admin_password,
)
from modules.identity._commercial_context_service import (
    scope_from_admin_principal,
    scope_from_device_principal,
)
from modules.identity.adapters import device_identity as device_identity_repository
from modules.identity.adapters import postgres as admin_identity_repository

__all__ = [
    "AdminAuthenticationError",
    "AdminAuthorizationError",
    "admin_identity_repository",
    "admin_identity_service",
    "device_identity_repository",
    "device_identity_service",
    "fleet_management_service",
    "admin_password_needs_rehash",
    "authenticate_admin_session",
    "authorize_admin_action",
    "hash_admin_password",
    "hash_admin_session_token",
    "login_admin",
    "logout_admin",
    "normalize_admin_login",
    "rotate_admin_session",
    "scope_from_admin_principal",
    "scope_from_device_principal",
    "sync_admin_permission_catalog",
    "verify_admin_password",
]
