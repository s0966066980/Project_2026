"""Project analysis, as the UI API is allowed to perform it.

This module used to call the LLM gateway on a worker thread and generate
proposals in-process. Both are gone. ADR-0036 puts provider execution in the
`project-analyst` sidecar, and ADR-0034 leaves this process with read-only
evidence and nothing that executes.

What remains here is coordination: read allowlisted evidence, hand it across
the process boundary, and store one report. No CLI, no shell, no filesystem
write outside the report, and no provider call.
"""

from __future__ import annotations

from typing import Any

from project_analysis import report_store, sidecar_client, snapshot
from project_analysis.sidecar_client import SidecarUnavailable

import config

__all__ = [
    "SidecarUnavailable",
    "analyze",
    "latest_report",
    "ready_models",
    "status",
]


def ready_models() -> list[dict[str, Any]]:
    """The Project Analyst Profiles, ready or not.

    Unready profiles are included with their reason. An empty selector tells an
    operator nothing; `credential_missing` tells them what to do.
    """

    try:
        return sidecar_client.profiles()
    except SidecarUnavailable as unavailable:
        return [{"id": "", "ready": False, "reason": str(unavailable)}]


def latest_report() -> dict[str, Any] | None:
    return report_store.load()


def status() -> dict[str, Any]:
    return {"models": ready_models(), "latest": latest_report()}


async def analyze(profile: str, *, readiness: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run one analysis with one explicitly chosen profile.

    A failure never discards the previous report: it marks it stale and raises.
    Returning the old report as though it were fresh, or silently retrying with
    another provider, are the two ways this operation could lie about what it
    knows.
    """

    built = snapshot.build_snapshot(environment=config.APP_ENV, readiness=readiness)
    try:
        result = sidecar_client.analyze(profile=profile, snapshot=built.payload)
    except SidecarUnavailable as unavailable:
        report_store.mark_stale(str(unavailable))
        raise

    stored = report_store.replace(result)
    # Skipped evidence is local diagnostics: it tells an operator which paths
    # the allowlist refused, and it is deliberately not part of the stored
    # report or of anything the provider ever saw.
    return {**stored, "skipped_evidence": built.skipped}
