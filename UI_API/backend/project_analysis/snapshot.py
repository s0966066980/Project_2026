"""Assemble the one thing the Project Analyst Sidecar is allowed to see.

The sidecar has no repository mount, so a snapshot is not a pointer to files —
it is the files, already read and already filtered. Everything in it came
through `evidence.read_evidence`, which means a path that the allowlist refuses
cannot reach a provider even if something here asks for it.

Snapshots are built only on an explicit Admin request
([ADR-0035](../../../docs/adr/0035-create-project-analysis-snapshots-only-on-explicit-request.md));
nothing in this module runs on a schedule or on startup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from . import evidence

# The project shape a reviewer would ask for first: what the system claims to
# be, how it is deployed, and the contracts it says it holds itself to. Paths
# that do not exist are skipped rather than failing the snapshot, so the set can
# name a file the repository has not grown yet.
DEFAULT_EVIDENCE_PATHS: tuple[str, ...] = (
    "CONTEXT.md",
    "AGENTS.md",
    "README.md",
    "Project_2026_Execution_Plan.md",
    "docker/compose.yaml",
    "docker/compose.pilot.yaml",
    "docker/compose.project-analyst.yaml",
    "docker/Dockerfile",
    "UI_API/backend/capabilities/manifest.py",
    "UI_API/backend/project_analysis/evidence.py",
    "UI_API/backend/api/route_registry.py",
)

# Well below the sidecar's own bound, because the snapshot crosses a process
# boundary on an Admin request and a slow one is a stalled Admin page.
MAX_SNAPSHOT_FILES = 60


def _git_revision() -> str:
    """The revision this build is, or `unknown`.

    Baked in at build time rather than shelled out for. The runtime image has no
    Git and no repository — asking at runtime returned `unknown` every time,
    which is the kind of always-on fallback that looks like a working feature.

    It is also the more correct answer: for a digest-pinned immutable artifact
    the revision is a property of the image, not of whatever working tree
    happens to be mounted next to it. And it keeps `subprocess` out of the UI
    API process entirely, which is what ADR-0034 asks of this capability.

    `unknown` stays a legitimate value. A report that cannot name its revision
    is still useful; one that guesses is not.
    """

    revision = str(os.getenv("APP_GIT_REVISION", "") or "").strip()
    if not revision or len(revision) > 64 or not revision.isalnum():
        return "unknown"
    return revision


@dataclass(frozen=True)
class BuiltSnapshot:
    """A snapshot and the local record of what did not go into it.

    `payload` is exactly what crosses to the sidecar, which validates it with
    `extra="forbid"`. `skipped` never leaves this process: an operator needs to
    know a path was excluded and by which rule, and a provider does not.
    """

    payload: dict[str, Any]
    skipped: list[dict[str, str]]


def build_snapshot(
    *,
    environment: str,
    readiness: dict[str, Any] | None = None,
    evidence_paths: tuple[str, ...] | None = None,
) -> BuiltSnapshot:
    """Build a sanitized Project Analysis Snapshot.

    Every requested path goes through the evidence allowlist. A refused path is
    dropped and recorded by rule, so an operator can see that something was
    excluded and why, without the refusal itself becoming a way to probe the
    filesystem.
    """

    requested = evidence_paths if evidence_paths is not None else DEFAULT_EVIDENCE_PATHS
    collected: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for path in requested[:MAX_SNAPSHOT_FILES]:
        try:
            item = evidence.read_evidence(path)
        except evidence.EvidenceNotAllowed as refusal:
            skipped.append({"path": path, "reason": str(refusal)})
            continue
        collected.append({"path": item.path, "size_bytes": item.size_bytes, "text": item.text})

    payload = {
        "snapshot_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": _git_revision(),
        "environment": environment,
        # Readiness is a projection the caller supplies. It carries capability
        # status, never configuration values, so a snapshot cannot become a
        # settings dump on its way to a provider.
        "readiness": readiness or {},
        "evidence": collected,
    }
    return BuiltSnapshot(payload=payload, skipped=skipped)
