"""Audited Admin role and permission management application service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from models.admin_identity import AdminPrincipal
from models.commercial_scope import CommercialScope
from modules.identity.adapters import postgres as admin_identity_repository
from modules.identity._admin_authorization_service import authorize_admin_action
from repositories import admin_audit_repository


def _record_access_change(
    principal: AdminPrincipal,
    scope: CommercialScope,
    action: str,
    target_type: str,
    target_id: UUID,
    metadata: dict[str, str],
) -> None:
    admin_audit_repository.append_admin_audit_scoped(
        {
            "audit_id": f"aud_{uuid4().hex}",
            "actor": str(principal.user_id),
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id),
            "metadata": metadata,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        scope,
    )


def assign_admin_role(
    principal: AdminPrincipal,
    scope: CommercialScope,
    *,
    user_id: UUID,
    role_id: UUID,
    store_id: UUID | None,
) -> dict:
    authorize_admin_action(principal, "admin_identity.manage", scope)
    if store_id is not None and store_id != scope.store_id:
        raise ValueError("Role assignment store must match the authorized scope")
    assignment = admin_identity_repository.assign_admin_role(
        assignment_id=uuid4(),
        tenant_id=scope.tenant_id,
        user_id=user_id,
        role_id=role_id,
        store_id=store_id,
    )
    _record_access_change(
        principal,
        scope,
        "admin_role_assignment_changed",
        "admin_user",
        user_id,
        {"role_id": str(role_id), "store_id": str(store_id) if store_id else "tenant"},
    )
    return assignment


def grant_role_permission(
    principal: AdminPrincipal,
    scope: CommercialScope,
    *,
    role_id: UUID,
    permission_id: UUID,
    permission_name: str,
) -> None:
    authorize_admin_action(principal, "admin_identity.manage", scope)
    admin_identity_repository.grant_permission_to_role(scope.tenant_id, role_id, permission_id)
    _record_access_change(
        principal,
        scope,
        "admin_permission_changed",
        "admin_role",
        role_id,
        {"permission": permission_name},
    )
