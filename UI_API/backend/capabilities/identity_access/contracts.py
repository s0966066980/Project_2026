"""Published identity and device-access vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class IdentityCapabilityError(RuntimeError):
    """Safe, transport-independent identity failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AccessGrant:
    principal_id: UUID
    tenant_id: UUID
    store_ids: tuple[UUID, ...]
    permissions: tuple[str, ...]
    expires_at: datetime | None = None
