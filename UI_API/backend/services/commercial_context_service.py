"""Convert verified identities into explicit commercial repository scope."""

from uuid import UUID

from models.admin_identity import AdminPrincipal
from models.commercial_scope import CommercialScope
from models.device_identity import DevicePrincipal


def scope_from_admin_principal(
    principal: AdminPrincipal,
    store_id: UUID | None = None,
) -> CommercialScope:
    resolved_store = store_id or (principal.allowed_store_ids[0] if principal.allowed_store_ids else None)
    if resolved_store is None or resolved_store not in principal.allowed_store_ids:
        raise PermissionError("Admin store scope is not allowed")
    return CommercialScope(principal.tenant_id, resolved_store)


def scope_from_device_principal(principal: DevicePrincipal) -> CommercialScope:
    return CommercialScope(principal.tenant_id, principal.store_id, principal.device_id)
