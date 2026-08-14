from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityRegistration:
    name: str
    schema_requirement: str
    adapters: frozenset[str]


def capability_registry() -> tuple[CapabilityRegistration, ...]:
    both = frozenset({"postgresql", "sqlite"})
    postgresql = frozenset({"postgresql"})
    return (
        CapabilityRegistration("admin_identity", "0005", postgresql),
        CapabilityRegistration("device_identity", "0005", postgresql),
        CapabilityRegistration("member", "0012", postgresql),
        CapabilityRegistration("commercial_settings", "0007", postgresql),
        CapabilityRegistration("availability", "0007", postgresql),
        CapabilityRegistration("promotion", "0007", postgresql),
        CapabilityRegistration("campaign", "0007", postgresql),
        CapabilityRegistration("recommendation_event", "0007", postgresql),
        CapabilityRegistration("interaction_event", "0007", postgresql),
        CapabilityRegistration("ordering_session", "0007", postgresql),
        CapabilityRegistration("worker_job_and_outbox", "0007", postgresql),
        CapabilityRegistration("object_metadata", "0007", postgresql),
        CapabilityRegistration("knowledge_publication", "0017", both),
        CapabilityRegistration("retrieval_configuration", "0027", both),
        CapabilityRegistration("voice_turn", "0018", both),
        CapabilityRegistration("checkout_confirmation_and_cart", "0022", both),
        CapabilityRegistration("ordering_entry", "0020", both),
        CapabilityRegistration("retrieval_check", "0021", both),
        CapabilityRegistration("optimization_lab", "0030", both),
        CapabilityRegistration("admin_audit", "0007", postgresql),
    )


def adapter_coverage(backend: str) -> dict[str, object]:
    registrations = capability_registry()
    missing = [item.name for item in registrations if backend not in item.adapters]
    return {
        "backend": backend,
        "registered": len(registrations),
        "covered": len(registrations) - len(missing),
        "complete": not missing,
        "missing": missing,
        "capabilities": [item.name for item in registrations],
    }
