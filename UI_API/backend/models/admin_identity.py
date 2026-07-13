"""Typed Admin identity and authorization contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

AdminAuthMethod = Literal["session", "legacy_token"]


@dataclass(frozen=True)
class AdminPrincipal:
    user_id: UUID
    tenant_id: UUID
    allowed_store_ids: tuple[UUID, ...]
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    session_id: UUID | None
    auth_method: AdminAuthMethod

    def has_permission(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions


@dataclass(frozen=True)
class AdminSessionResult:
    token: str
    principal: AdminPrincipal
    expires_at: datetime
