"""The only published Admin identity surface for capability consumers."""

from capabilities.identity_access.contracts import AccessGrant, IdentityCapabilityError
from modules.identity.application import (
    AdminAuthenticationError,
    AdminAuthorizationError,
    authenticate_admin_session,
    authorize_admin_action,
    device_identity_repository,
    device_identity_service,
    fleet_management_service,
    hash_admin_password,
    hash_admin_session_token,
    login_admin,
    logout_admin,
    normalize_admin_login,
    rotate_admin_session,
    scope_from_admin_principal,
    scope_from_device_principal,
    sync_admin_permission_catalog,
    verify_admin_password,
)

# Device credentials, fleet commands and scope resolution used to be reached
# through call-time proxies into services/, which is what kept this capability
# on the legacy horizontal layers. They now live inside modules/identity and are
# published directly, so the surface says what it owns instead of forwarding.


def device_admin_principal(request):
    """Resolve the device-authenticated Admin principal for transport adapters."""

    from utils.auth_utils import device_admin_principal as resolve

    return resolve(request)


__all__ = [
    "AccessGrant",
    "device_identity_repository",
    "AdminAuthenticationError",
    "AdminAuthorizationError",
    "IdentityCapabilityError",
    "authenticate_admin_session",
    "authorize_admin_action",
    "device_identity_service",
    "device_admin_principal",
    "fleet_management_service",
    "scope_from_admin_principal",
    "scope_from_device_principal",
    "hash_admin_password",
    "hash_admin_session_token",
    "login_admin",
    "logout_admin",
    "normalize_admin_login",
    "rotate_admin_session",
    "sync_admin_permission_catalog",
    "verify_admin_password",
]
