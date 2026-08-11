"""One report, replaced atomically, or kept and marked stale.

[ADR-0038](../../../docs/adr/0038-retain-only-the-latest-project-analysis-report.md):
each project retains only its latest successful report. A successful rescan
atomically replaces and permanently deletes the previous one. A failed rescan
leaves the previous report available but marks it stale and records only a safe
failure reason.

Both halves matter. Without atomic replacement a crash mid-write leaves a
half-written report that reads as current. Without the stale mark a failed
rescan leaves an old report looking freshly confirmed, which is the more
dangerous of the two — nobody checks the timestamp on a report that appears to
have just succeeded.

Sanitized source input, CLI event streams and model reasoning are never
persisted. Only the structured result is.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import config

REPORT_FILENAME = "project_analysis_latest.json"

# The report is a structured result, not a transcript. Anything approaching this
# is a provider returning prose it was told not to return.
MAX_REPORT_BYTES = 512 * 1024


def _report_path() -> str:
    return os.path.join(config.LEARNING_DATA_DIR, REPORT_FILENAME)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load() -> dict[str, Any] | None:
    """The latest report, or None. A corrupt file reads as absent, never as partial."""

    try:
        with open(_report_path(), encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def replace(result: dict[str, Any]) -> dict[str, Any]:
    """Replace the latest report atomically.

    `os.replace` is the whole mechanism: on POSIX it is a rename, so a reader
    sees either the previous report or the new one and never a partial write.
    The previous report is gone once it returns — this store keeps one.
    """

    report = {
        "status": "current",
        "recorded_at": _now(),
        "result": result,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if len(serialized.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("project_analysis_report_too_large")

    path = _report_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return report


def mark_stale(reason: str) -> dict[str, Any] | None:
    """Record that a rescan failed, without discarding the previous report.

    The report itself is untouched; only its status and the safe failure reason
    change. If there is no previous report there is nothing to mark, and the
    caller's failure is already visible on its own.
    """

    existing = load()
    if existing is None:
        return None

    existing["status"] = "stale"
    existing["stale_since"] = _now()
    # A reason code, never a provider error body: this file is projected to the
    # Admin surface and must not become a place raw output accumulates.
    existing["stale_reason"] = str(reason)[:120]

    path = _report_path()
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(existing, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return existing
