"""Server-resolved commercial ownership scopes."""

from dataclasses import dataclass
from uuid import UUID, uuid4

LEGACY_DEFAULT_TENANT_ID = UUID("00000000-0000-4000-8000-000000000001")
LEGACY_DEFAULT_STORE_ID = UUID("00000000-0000-4000-8000-000000000002")
LEGACY_DEFAULT_DEVICE_ID = UUID("00000000-0000-4000-8000-000000000003")


class CommercialScopeConflictError(ValueError):
    """A globally unique commercial identifier belongs to another scope."""

    pass


def new_commercial_id() -> UUID:
    """Generate application-owned Tenant, Store, or Device identifiers."""

    return uuid4()


@dataclass(frozen=True)
class TenantScope:
    tenant_id: UUID


@dataclass(frozen=True)
class StoreScope:
    tenant_id: UUID
    store_id: UUID


@dataclass(frozen=True)
class DeviceScope:
    tenant_id: UUID
    store_id: UUID
    device_id: UUID


@dataclass(frozen=True)
class CommercialScope:
    tenant_id: UUID
    store_id: UUID
    device_id: UUID | None = None

    def __post_init__(self) -> None:
        for name, value in (("tenant_id", self.tenant_id), ("store_id", self.store_id)):
            if not isinstance(value, UUID):
                raise TypeError(f"{name} must be a UUID")
        if self.device_id is not None and not isinstance(self.device_id, UUID):
            raise TypeError("device_id must be a UUID or None")

    @property
    def tenant_scope(self) -> TenantScope:
        return TenantScope(self.tenant_id)

    @property
    def store_scope(self) -> StoreScope:
        return StoreScope(self.tenant_id, self.store_id)

    @property
    def device_scope(self) -> DeviceScope | None:
        if self.device_id is None:
            return None
        return DeviceScope(self.tenant_id, self.store_id, self.device_id)


LEGACY_DEFAULT_SCOPE = CommercialScope(
    tenant_id=LEGACY_DEFAULT_TENANT_ID,
    store_id=LEGACY_DEFAULT_STORE_ID,
    device_id=LEGACY_DEFAULT_DEVICE_ID,
)


def is_legacy_tenant_scope(scope: CommercialScope) -> bool:
    return scope.tenant_id == LEGACY_DEFAULT_TENANT_ID


def is_legacy_store_scope(scope: CommercialScope) -> bool:
    return is_legacy_tenant_scope(scope) and scope.store_id == LEGACY_DEFAULT_STORE_ID


def is_legacy_device_scope(scope: CommercialScope) -> bool:
    return is_legacy_store_scope(scope) and scope.device_id == LEGACY_DEFAULT_DEVICE_ID
