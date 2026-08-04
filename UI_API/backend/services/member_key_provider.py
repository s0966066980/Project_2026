"""Versioned Member PII key provider port and local/environment adapters."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Protocol


class MemberKeyConfigurationError(RuntimeError):
    """Member PII key material is unavailable or malformed."""


@dataclass(frozen=True)
class MemberKeyMaterial:
    version: str
    lookup_pepper: bytes
    encryption_key: bytes


class MemberKeyProvider(Protocol):
    @property
    def active_version(self) -> str: ...

    def material(self, version: str | None = None) -> MemberKeyMaterial: ...


def _development_material(version: str) -> MemberKeyMaterial:
    lookup_pepper = hashlib.sha256(f"Project_2026 development lookup {version}".encode()).digest()
    encryption_key = base64.urlsafe_b64encode(
        hashlib.sha256(f"Project_2026 development encryption {version}".encode()).digest()
    )
    return MemberKeyMaterial(version, lookup_pepper, encryption_key)


class DevelopmentMemberKeyProvider:
    """Deterministic, non-production provider for development and tests only."""

    def __init__(self, active_version: str = "v1") -> None:
        if active_version not in {"v1", "v2"}:
            raise MemberKeyConfigurationError("Unsupported development Member key version")
        self._active_version = active_version

    @property
    def active_version(self) -> str:
        return self._active_version

    def material(self, version: str | None = None) -> MemberKeyMaterial:
        resolved = version or self.active_version
        if resolved not in {"v1", "v2"}:
            raise MemberKeyConfigurationError("Member key version is unavailable")
        return _development_material(resolved)


class EnvironmentMemberKeyProvider:
    """Load a versioned keyring from deployment-owned environment secrets."""

    def __init__(self) -> None:
        self._active_version = str(os.getenv("MEMBER_PHONE_KEY_VERSION", "") or "").strip()
        try:
            lookup_ring = self._load_ring(
                "MEMBER_PHONE_LOOKUP_PEPPERS_JSON",
                "MEMBER_PHONE_LOOKUP_PEPPER",
            )
            encryption_ring = self._load_ring(
                "MEMBER_PHONE_ENCRYPTION_KEYS_JSON",
                "MEMBER_PHONE_ENCRYPTION_KEY",
            )
            if (
                not self._active_version
                or self._active_version not in lookup_ring
                or self._active_version not in encryption_ring
            ):
                raise ValueError
            self._materials = {
                version: MemberKeyMaterial(
                    version=version,
                    lookup_pepper=lookup_ring[version].encode(),
                    encryption_key=encryption_ring[version].encode(),
                )
                for version in lookup_ring.keys() & encryption_ring.keys()
            }
            for material in self._materials.values():
                if len(material.lookup_pepper) < 32:
                    raise ValueError
                decoded = base64.urlsafe_b64decode(material.encryption_key)
                if len(decoded) != 32:
                    raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MemberKeyConfigurationError("Member PII key material is unavailable or invalid") from exc

    @staticmethod
    def _load_ring(ring_name: str, single_name: str) -> dict[str, str]:
        raw_ring = str(os.getenv(ring_name, "") or "").strip()
        if raw_ring:
            parsed = json.loads(raw_ring)
            if not isinstance(parsed, dict):
                raise ValueError
            return {str(key): str(value) for key, value in parsed.items() if key and value}
        active = str(os.getenv("MEMBER_PHONE_KEY_VERSION", "") or "").strip()
        value = str(os.getenv(single_name, "") or "").strip()
        return {active: value} if active and value else {}

    @property
    def active_version(self) -> str:
        return self._active_version

    def material(self, version: str | None = None) -> MemberKeyMaterial:
        resolved = version or self.active_version
        try:
            return self._materials[resolved]
        except KeyError as exc:
            raise MemberKeyConfigurationError("Member key version is unavailable") from exc
