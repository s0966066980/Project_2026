"""The only published Admin identity surface for capability consumers."""

from capabilities.identity_access.contracts import AccessGrant, IdentityCapabilityError
from models.commercial_scope import CommercialScope
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


class _DeviceIdentityProxy:
    """Bind device credential operations through the Identity capability surface."""

    def __getattr__(self, name: str):
        from services import device_identity_service

        return getattr(device_identity_service, name)


device_identity_service = _DeviceIdentityProxy()


class _FleetManagementServiceProxy:
    def __getattr__(self, name: str):
        from services import fleet_management_service

        return getattr(fleet_management_service, name)


fleet_management_service = _FleetManagementServiceProxy()


def scope_from_admin_principal(principal) -> CommercialScope:
    from services.commercial_context_service import scope_from_admin_principal as resolve

    return resolve(principal)


def scope_from_device_principal(principal) -> CommercialScope:
    from services.commercial_context_service import scope_from_device_principal as resolve

    return resolve(principal)


def device_admin_principal(request):
    """Resolve the device-authenticated Admin principal for transport adapters."""

    from utils.auth_utils import device_admin_principal as resolve

    return resolve(request)


__all__ = [
    "AccessGrant",
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
