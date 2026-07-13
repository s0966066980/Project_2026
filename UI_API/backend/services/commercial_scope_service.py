"""Application-facing commercial scope resolver."""

from collections.abc import Mapping

from models.commercial_scope import CommercialScope
from utils import commercial_scope_config

CommercialScopeConfigurationError = commercial_scope_config.CommercialScopeConfigurationError


def resolve_commercial_scope(
    untrusted_headers: Mapping[str, str] | None = None,
) -> CommercialScope:
    """Resolve scope from trusted server configuration, never raw headers."""

    return commercial_scope_config.resolve_commercial_scope(untrusted_headers)
