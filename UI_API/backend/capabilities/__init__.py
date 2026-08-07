"""Business capability packages and their migration manifest."""

from .manifest import CAPABILITIES, CapabilityDefinition, capability_by_key

__all__ = ["CAPABILITIES", "CapabilityDefinition", "capability_by_key"]
