"""The Project Analyst Sidecar.

A separate service and a separate image, because the alternative is installing
Codex, Claude or Grok into the App and Worker images and giving a provider CLI
the same process, filesystem and network reach as the ordering system
([ADR-0036](../docs/adr/0036-run-project-analysis-in-a-dedicated-sidecar.md)).

It receives a sanitized Project Analysis Snapshot, invokes exactly one
allowlisted non-interactive provider, and returns one common structured result.
It has no repository mount, no database, no user home, no Docker socket, and no
way to change project or runtime state.
"""

from .contract import (
    AnalysisFinding,
    AnalysisRequest,
    AnalysisResult,
    ProfileStatus,
    ProjectAnalysisSnapshot,
    SnapshotEvidence,
)

__all__ = [
    "AnalysisFinding",
    "AnalysisRequest",
    "AnalysisResult",
    "ProfileStatus",
    "ProjectAnalysisSnapshot",
    "SnapshotEvidence",
]
