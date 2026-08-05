"""Target capability map used by architecture checks during migration."""

from dataclasses import dataclass
from typing import Literal

CapabilityCriticality = Literal["core", "operational", "optional"]


@dataclass(frozen=True)
class CapabilityDefinition:
    key: str
    display_name: str
    criticality: CapabilityCriticality
    migration_wave: int


CAPABILITIES: tuple[CapabilityDefinition, ...] = (
    CapabilityDefinition("catalog", "Catalog & Availability", "core", 1),
    CapabilityDefinition("identity_access", "Identity & Device Access", "core", 1),
    CapabilityDefinition("operations_configuration", "Operations & Configuration", "core", 1),
    CapabilityDefinition("member", "Member", "operational", 2),
    CapabilityDefinition("campaign_promotion", "Campaign & Promotion", "operational", 2),
    CapabilityDefinition(
        "recommendation_analytics",
        "Recommendation & Interaction Analytics",
        "optional",
        2,
    ),
    CapabilityDefinition("ordering", "Ordering & Checkout", "core", 3),
    CapabilityDefinition("knowledge_rag", "Knowledge/RAG", "optional", 4),
    CapabilityDefinition("voice", "Voice Assistance", "optional", 4),
    CapabilityDefinition("emotion", "Emotion Diagnostics", "optional", 4),
)


def capability_by_key(key: str) -> CapabilityDefinition:
    for capability in CAPABILITIES:
        if capability.key == key:
            return capability
    raise KeyError(key)
