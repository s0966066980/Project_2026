"""Stable contracts for the P4 Optimization Lab.

The lab deliberately has a smaller vocabulary than the customer capabilities.
It can describe evidence and a reference report, but it cannot express a
production mutation, a prompt replacement, or a published recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ANALYZER_DATA_SCOPES = ("synthetic_only", "customer_evidence")
EVIDENCE_LEVELS = ("Observation Signal", "Reference Guidance", "Insufficient Evidence")
FINDING_CLASSIFICATIONS = (
    "RAG Knowledge Gap",
    "Prompt Behavior",
    "Model Capability",
    "Product Pipeline",
    "Insufficient Evidence",
)
REPORT_SECTIONS = (
    "api_connectivity",
    "commercial_outcomes",
    "voice_outcomes",
    "rag_observations",
    "voice_interaction_analysis",
    "findings_and_guidance",
)


class OptimizationLabError(ValueError):
    """A caller-visible, safe Optimization Lab contract error."""

    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class AnalyzerProfile:
    """Provider-native options discovered for one installed analyzer."""

    profile_id: str
    provider: str
    version: str
    ready: bool
    models: tuple[str, ...]
    efforts: tuple[str, ...]
    data_scopes: tuple[str, ...]
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "provider": self.provider,
            "version": self.version,
            "ready": self.ready,
            "models": list(self.models),
            "efforts": list(self.efforts),
            "data_scopes": list(self.data_scopes),
            "reason": self.reason,
        }
