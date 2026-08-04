"""Typed Kiosk device identity and session contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

DeviceAuthMethod = Literal["device_session", "legacy_token"]


@dataclass(frozen=True)
class DevicePrincipal:
    device_id: UUID
    store_id: UUID
    tenant_id: UUID
    credential_id: UUID | None
    session_id: UUID | None
    issued_at: datetime
    expires_at: datetime
    auth_method: DeviceAuthMethod


@dataclass(frozen=True)
class DeviceSessionResult:
    token: str
    principal: DevicePrincipal


@dataclass(frozen=True)
class DeviceCredentialIssue:
    credential_id: UUID
    key_id: str
    credential: str
    expires_at: datetime
