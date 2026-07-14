"""Identity module — Admin authentication, RBAC, sessions."""

from modules.identity.application import (
    AdminAuthenticationError,
    AdminAuthorizationError,
    authenticate_admin_session,
    authorize_admin_action,
    hash_admin_password,
    hash_admin_session_token,
    login_admin,
    logout_admin,
    normalize_admin_login,
    rotate_admin_session,
    sync_admin_permission_catalog,
    verify_admin_password,
)

__all__ = [
    "AdminAuthenticationError",
    "AdminAuthorizationError",
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
