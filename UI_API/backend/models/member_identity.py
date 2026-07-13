"""Typed Member UUID and protected-phone contracts."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ProtectedPhone:
    phone_lookup_hash: str
    phone_encrypted: str
    phone_masked: str
    key_version: str


@dataclass(frozen=True)
class MemberIdentity:
    member_id: UUID
    tenant_id: UUID
    phone_masked: str
    key_version: str
