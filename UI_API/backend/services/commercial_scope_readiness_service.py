"""Read-only configured commercial scope readiness validation."""

from dataclasses import dataclass

from models.commercial_scope import CommercialScope
from repositories import postgres_utils
from services.commercial_scope_service import resolve_commercial_scope


class CommercialScopeReadinessError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommercialScopeReadiness:
    scope: CommercialScope
    is_ready: bool = True


def validate_configured_commercial_scope(scope: CommercialScope | None = None) -> CommercialScopeReadiness:
    """Verify an active Tenant → Store → Device hierarchy without modifying data."""

    resolved_scope = scope or resolve_commercial_scope()
    if resolved_scope.device_id is None:
        raise CommercialScopeReadinessError("configured device scope is required")
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    tenants.status AS tenant_status,
                    stores.tenant_id AS store_tenant_id,
                    stores.status AS store_status,
                    devices.tenant_id AS device_tenant_id,
                    devices.store_id AS device_store_id,
                    devices.status AS device_status
                FROM tenants
                LEFT JOIN stores ON stores.id = %s
                LEFT JOIN devices ON devices.id = %s
                WHERE tenants.id = %s
                """,
                (resolved_scope.store_id, resolved_scope.device_id, resolved_scope.tenant_id),
            )
            row = cur.fetchone()
    if row is None:
        raise CommercialScopeReadinessError("configured tenant does not exist")
    if str(row.get("tenant_status") or "").lower() != "active":
        raise CommercialScopeReadinessError("configured tenant is not active")
    if row.get("store_tenant_id") != resolved_scope.tenant_id or str(row.get("store_status") or "").lower() != "active":
        raise CommercialScopeReadinessError("configured store is missing, inactive, or belongs to another tenant")
    if (
        row.get("device_tenant_id") != resolved_scope.tenant_id
        or row.get("device_store_id") != resolved_scope.store_id
        or str(row.get("device_status") or "").lower() != "active"
    ):
        raise CommercialScopeReadinessError("configured device is missing, inactive, or belongs to another store")
    return CommercialScopeReadiness(scope=resolved_scope)
