"""Public Application API for the identity module."""

from __future__ import annotations

# Temporary re-export of internal implementation for tests mid-cutover.
from modules.identity import _admin_identity_service as admin_identity_service
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
from modules.identity.adapters import postgres as admin_identity_repository

__all__ = [
    "AdminAuthenticationError",
    "AdminAuthorizationError",
    "admin_identity_repository",
    "admin_identity_service",
    "admin_password_needs_rehash",
    "authenticate_admin_session",
    "authorize_admin_action",
    "hash_admin_password",
    "hash_admin_session_token",
    "login_admin",
    "logout_admin",
    "normalize_admin_login",
    "rotate_admin_session",
    "sync_admin_permission_catalog",
    "verify_admin_password",
]
