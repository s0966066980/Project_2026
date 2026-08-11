"""The contract between the UI API and the Project Analyst Sidecar.

The sidecar has no repository mount, no database, no user home and no Docker
socket ([ADR-0036](../docs/adr/0036-run-project-analysis-in-a-dedicated-sidecar.md)).
Everything it is allowed to see arrives in the request body as an already
sanitized Project Analysis Snapshot, and everything it returns is this common
structured result regardless of which provider produced it.

The snapshot validation here deliberately repeats work the UI API already did
with its evidence allowlist. That duplication is the point: the sidecar is the
process that talks to an external provider, so it does not take the caller's
word for what is safe to forward.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SNAPSHOT_VERSION = "1"

MAX_EVIDENCE_FILES = 400
MAX_EVIDENCE_BYTES_TOTAL = 4 * 1024 * 1024

# Mirrors the UI API allowlist rather than importing it. The sidecar must stay
# able to refuse a malformed snapshot even if the caller is compromised or
# simply wrong, so it repeats the checks that keep a path inside the project.
DENIED_PATH_FRAGMENTS: tuple[str, ...] = (
    "..",
    "~",
    ".env",
    "id_rsa",
    "id_ed25519",
    ".pem",
    ".key",
    "credential",
    "secret",
    "password",
    "passwd",
    "token",
    "node_modules",
    "learning_data",
    "runtime_data",
    "/.git/",
)

Severity = Literal["healthy", "warning", "blocked"]


class SnapshotEvidence(BaseModel):
    """One allowlisted project file, as the UI API read it."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(ge=0)
    text: str

    @field_validator("path")
    @classmethod
    def path_must_stay_inside_the_project(cls, value: str) -> str:
        candidate = value.replace("\\", "/")
        if candidate.startswith("/"):
            raise ValueError("evidence path must be repository-relative")
        lowered = f"/{candidate.lower()}/"
        for fragment in DENIED_PATH_FRAGMENTS:
            if fragment in lowered:
                raise ValueError(f"evidence path is not analysable: {fragment}")
        return candidate


class ProjectAnalysisSnapshot(BaseModel):
    """Everything the sidecar is permitted to know about the project."""

    model_config = ConfigDict(extra="forbid")

    snapshot_version: str = Field(default=SNAPSHOT_VERSION)
    generated_at: str = Field(min_length=1, max_length=64)
    git_revision: str = Field(min_length=1, max_length=64)
    environment: str = Field(min_length=1, max_length=32)
    readiness: dict[str, object] = Field(default_factory=dict)
    evidence: list[SnapshotEvidence] = Field(default_factory=list)

    @field_validator("snapshot_version")
    @classmethod
    def only_the_known_version(cls, value: str) -> str:
        if value != SNAPSHOT_VERSION:
            raise ValueError(f"unsupported snapshot version: {value}")
        return value

    @field_validator("evidence")
    @classmethod
    def bounded_evidence(cls, value: list[SnapshotEvidence]) -> list[SnapshotEvidence]:
        if len(value) > MAX_EVIDENCE_FILES:
            raise ValueError("snapshot carries too many evidence files")
        total = sum(item.size_bytes for item in value)
        if total > MAX_EVIDENCE_BYTES_TOTAL:
            raise ValueError("snapshot exceeds the evidence size bound")
        paths = [item.path for item in value]
        if len(set(paths)) != len(paths):
            raise ValueError("snapshot repeats an evidence path")
        return value


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str = Field(min_length=1, max_length=32)
    snapshot: ProjectAnalysisSnapshot


class AnalysisFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=4000)
    evidence_paths: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """The one shape every provider returns.

    Nothing provider-specific survives into the report: no CLI event stream, no
    model reasoning, no follow-up conversation
    ([ADR-0038](../docs/adr/0038-retain-only-the-latest-project-analysis-report.md)).
    """

    model_config = ConfigDict(extra="forbid")

    profile: str
    observed_at: str
    git_revision: str
    findings: list[AnalysisFinding] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)


class ProfileStatus(BaseModel):
    """Why a Project Analyst Profile is or is not selectable.

    A profile that fails any readiness condition is not selectable and reports a
    bounded reason ([ADR-0037](../docs/adr/0037-select-only-ready-project-analyst-profiles.md)).
    The reason is a stable code, never a raw CLI error, so a failing probe cannot
    leak a credential path or an environment dump into the Admin surface.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    command: str
    ready: bool
    version: str = ""
    reason: str = ""
