"""Trusted server configuration adapter for commercial scope."""

from collections.abc import Mapping
from uuid import UUID

import config
from models.commercial_scope import LEGACY_DEFAULT_SCOPE, CommercialScope


class CommercialScopeConfigurationError(RuntimeError):
    pass


def _configured_uuid(name: str, default: UUID | None) -> UUID:
    raw = str(config.get(name, "") or "").strip()
    if not raw:
        if default is not None:
            return default
        raise CommercialScopeConfigurationError(f"{name} is required in production")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise CommercialScopeConfigurationError(f"{name} must be a valid UUID") from exc


def resolve_commercial_scope(
    _untrusted_headers: Mapping[str, str] | None = None,
) -> CommercialScope:
    """Return server scope and deliberately ignore unverified client headers."""

    defaults = None if config.is_production() else LEGACY_DEFAULT_SCOPE
    return CommercialScope(
        tenant_id=_configured_uuid("DEFAULT_TENANT_ID", defaults.tenant_id if defaults else None),
        store_id=_configured_uuid("DEFAULT_STORE_ID", defaults.store_id if defaults else None),
        device_id=_configured_uuid("DEFAULT_DEVICE_ID", defaults.device_id if defaults else None),
    )
