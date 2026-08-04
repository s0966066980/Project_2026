"""Centralized tenant/store-scoped Admin authorization policy."""

from models.admin_identity import AdminPrincipal
from models.commercial_scope import CommercialScope


class AdminAuthorizationError(PermissionError):
    pass


def authorize_admin_action(
    principal: AdminPrincipal,
    permission: str,
    scope: CommercialScope,
) -> AdminPrincipal:
    if principal.tenant_id != scope.tenant_id:
        raise AdminAuthorizationError("Admin tenant scope is not allowed")
    if scope.store_id not in principal.allowed_store_ids:
        raise AdminAuthorizationError("Admin store scope is not allowed")
    if not principal.has_permission(permission):
        raise AdminAuthorizationError("Admin permission is not allowed")
    return principal
