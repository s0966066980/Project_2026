"""The one gate through which project analysis may read anything.

[ADR-0034](../../../docs/adr/0034-bound-the-project-core-brain-to-read-only-evidence.md)
bounds the Project Core Brain to Git-tracked source, tests, documentation and
non-secret configuration inside this repository, and denies it `.env` files,
credentials, customer records, raw media, home-directory content and anything
outside the project.

That is a security boundary, so it is expressed as an allowlist and not as a
list of things to avoid. A denylist answers "is this one of the bad paths I
thought of"; an allowlist answers "is this one of the paths I decided to
expose", and only the second one stays correct when someone adds a directory.

Every read the analysis capability performs goes through `read_evidence`.
Nothing here executes, writes, or resolves outside the repository root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# A single file large enough to be worth reading and small enough that no
# snapshot can be turned into a bulk export of the repository.
MAX_EVIDENCE_BYTES = 256 * 1024

# Directory prefixes the capability may read, relative to the repository root.
# Adding one is a decision about what an analysis provider gets to see.
ALLOWED_PREFIXES: tuple[str, ...] = (
    "UI_API/backend",
    "UI_API/tests",
    "UI_API/frontend/admin",
    "UI_API/frontend/kiosk",
    "UI_API/frontend/shared",
    "UI_API/frontend/tests",
    "docs",
    "docker",
    "tools",
)

# Individual repository-root files that are project documentation rather than
# configuration with anything private in it.
ALLOWED_ROOT_FILES: frozenset[str] = frozenset(
    {
        "AGENTS.md",
        "CONTEXT.md",
        "README.md",
        "Project_2026_Execution_Plan.md",
    }
)

# Extensions worth reading as evidence. Anything else — archives, images,
# audio, video, model weights, databases — is refused by type rather than by
# hoping no allowlisted directory ever contains one.
ALLOWED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".md",
        ".html",
        ".css",
        ".sql",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".txt",
        "",  # extensionless files such as Dockerfile
    }
)

# Directories that sit inside an allowed prefix but hold generated output,
# dependencies or runtime state rather than project source.
DENIED_PATH_PARTS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "coverage",
        "test-results",
        "playwright-report",
        "learning_data",
        "runtime_data",
        "models",
        "secrets",
    }
)

# Name patterns that carry credentials regardless of where they live. A file
# matching one of these is refused even inside an allowed prefix.
DENIED_NAME_FRAGMENTS: tuple[str, ...] = (
    ".env",
    "id_rsa",
    "id_ed25519",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".keystore",
    "credential",
    "secret",
    "password",
    "passwd",
    "token",
    ".htpasswd",
)


class EvidenceNotAllowed(Exception):
    """A requested path is outside what project analysis may read.

    The message names the rule that refused it, never the resolved filesystem
    path, so a refusal cannot be used to probe what exists on the host.
    """


@dataclass(frozen=True)
class Evidence:
    """One allowlisted file, as project analysis is allowed to see it."""

    path: str
    size_bytes: int
    text: str


def _reject(rule: str) -> EvidenceNotAllowed:
    return EvidenceNotAllowed(f"evidence_not_allowed:{rule}")


def _normalized(relative_path: str) -> PurePosixPath:
    candidate = str(relative_path or "").strip()
    if not candidate:
        raise _reject("empty_path")
    if "\x00" in candidate:
        raise _reject("null_byte")
    # Windows-style separators would otherwise slip past the part checks below.
    posix = PurePosixPath(candidate.replace("\\", "/"))
    if posix.is_absolute():
        raise _reject("absolute_path")
    if any(part == ".." for part in posix.parts):
        raise _reject("parent_traversal")
    if any(part == "~" or part.startswith("~") for part in posix.parts):
        raise _reject("home_reference")
    return posix


def _check_allowlist(posix: PurePosixPath) -> None:
    text = posix.as_posix()
    if any(part in DENIED_PATH_PARTS for part in posix.parts):
        raise _reject("denied_directory")
    lowered = posix.name.lower()
    if any(fragment in lowered for fragment in DENIED_NAME_FRAGMENTS):
        raise _reject("credential_name")
    if posix.suffix.lower() not in ALLOWED_SUFFIXES:
        raise _reject("file_type")
    if len(posix.parts) == 1:
        if posix.name not in ALLOWED_ROOT_FILES:
            raise _reject("root_file_not_allowlisted")
        return
    if not any(text == prefix or text.startswith(f"{prefix}/") for prefix in ALLOWED_PREFIXES):
        raise _reject("outside_allowlist")


def _resolved_inside_repository(posix: PurePosixPath) -> Path:
    target = REPOSITORY_ROOT / Path(posix)
    # A symlink anywhere along the path can point outside the repository, so the
    # walk checks each component rather than trusting the final resolution.
    current = REPOSITORY_ROOT
    for part in posix.parts:
        current = current / part
        if current.is_symlink():
            raise _reject("symlink_component")
    resolved = target.resolve(strict=False)
    root = REPOSITORY_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise _reject("outside_repository")
    return resolved


def is_allowed(relative_path: str) -> bool:
    """Whether `read_evidence` would accept this path, without touching the disk."""

    try:
        _check_allowlist(_normalized(relative_path))
    except EvidenceNotAllowed:
        return False
    return True


def read_evidence(relative_path: str) -> Evidence:
    """Read one allowlisted repository file, or refuse with the rule that stopped it."""

    posix = _normalized(relative_path)
    _check_allowlist(posix)
    resolved = _resolved_inside_repository(posix)

    if not resolved.exists():
        raise _reject("not_found")
    if not resolved.is_file():
        raise _reject("not_a_regular_file")
    size = resolved.stat().st_size
    if size > MAX_EVIDENCE_BYTES:
        raise _reject("too_large")
    try:
        text = resolved.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as error:
        raise _reject("unreadable") from error
    return Evidence(path=posix.as_posix(), size_bytes=size, text=text)


def list_evidence(prefix: str, *, limit: int = 200) -> list[str]:
    """List readable evidence paths under one allowlisted prefix.

    Directory listing is bounded and goes through the same allowlist as reading,
    so it cannot be used to enumerate anything `read_evidence` would refuse.
    """

    posix = _normalized(prefix)
    text = posix.as_posix()
    if not any(text == allowed or text.startswith(f"{allowed}/") for allowed in ALLOWED_PREFIXES):
        raise _reject("outside_allowlist")
    root = _resolved_inside_repository(posix)
    if not root.is_dir():
        raise _reject("not_a_directory")

    found: list[str] = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in DENIED_PATH_PARTS]
        for filename in sorted(filenames):
            relative = Path(directory, filename).relative_to(REPOSITORY_ROOT).as_posix()
            if is_allowed(relative):
                found.append(relative)
                if len(found) >= limit:
                    return sorted(found)
    return sorted(found)
