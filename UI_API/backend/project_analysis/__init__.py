"""Project Core Brain support inside the UI API process.

This package holds only what the UI API is allowed to do for project analysis:
decide what evidence may be read, and assemble a sanitized Project Analysis
Snapshot from it. Running an analysis provider is not part of it — that belongs
to the dedicated `project-analyst` sidecar
([ADR-0036](../../../docs/adr/0036-run-project-analysis-in-a-dedicated-sidecar.md)),
which is the only place a Codex, Claude or Grok CLI is installed.

Project analysis is deliberately not one of the ten Business Capability Modules
in `capabilities/manifest.py`. It is a reference-only capability over the
project itself, kept separate from customer-facing work by
[ADR-0047](../../../docs/adr/0047-separate-project-analysis-from-customer-optimization-simulation.md),
and it must never appear in the Module Independence count.
"""

from .evidence import (
    Evidence,
    EvidenceNotAllowed,
    is_allowed,
    list_evidence,
    read_evidence,
)

__all__ = [
    "Evidence",
    "EvidenceNotAllowed",
    "is_allowed",
    "list_evidence",
    "read_evidence",
]
