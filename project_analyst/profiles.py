"""Discovery and readiness for the three Project Analyst Profiles.

ADR-0037: a profile is ready only when its CLI version satisfies the pinned
range, its automation credential is valid, non-interactive execution works, and
a contract probe returns the common result shape. A profile that fails any of
those is not selectable, reports a bounded reason, and is never substituted for
another one.

There is no fallback anywhere in this module. If the selected profile is not
ready, the run fails visibly. Silently reaching for a second provider would
mean an operator cannot tell which model produced a finding, which is the one
thing a report of this kind has to be able to say.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .contract import ProfileStatus

# Bounded because a readiness probe runs on an Admin request. A CLI that hangs
# must fail the probe, not hold the request open.
PROBE_TIMEOUT_SECONDS = 20

# Credentials arrive as Docker secrets, never as environment variables, so that
# an environment dump in a log or a diagnostic route cannot carry one.
SECRET_ROOT = Path(os.getenv("PROJECT_ANALYST_SECRET_ROOT", "/run/secrets"))


@dataclass(frozen=True)
class ProfileDefinition:
    """A provider CLI the sidecar is allowed to invoke."""

    id: str
    command: str
    version_argv: tuple[str, ...]
    # Inclusive lower bound and exclusive upper bound on the CLI major.minor.
    minimum_version: tuple[int, int]
    below_version: tuple[int, int]
    secret_name: str


PROFILES: tuple[ProfileDefinition, ...] = (
    ProfileDefinition("codex", "codex", ("--version",), (0, 40), (1, 0), "project_analyst_codex"),
    ProfileDefinition("claude", "claude", ("--version",), (1, 0), (3, 0), "project_analyst_claude"),
    ProfileDefinition("grok", "grok", ("--version",), (0, 1), (1, 0), "project_analyst_grok"),
)


def profile_by_id(profile_id: str) -> ProfileDefinition:
    for definition in PROFILES:
        if definition.id == profile_id:
            return definition
    raise KeyError(profile_id)


def _parse_version(text: str) -> tuple[int, int] | None:
    """Pull a major.minor out of whatever the CLI prints for --version."""

    digits: list[int] = []
    current = ""
    for character in text.strip():
        if character.isdigit():
            current += character
            continue
        if current:
            digits.append(int(current))
            current = ""
        if character not in "." and digits:
            break
    if current:
        digits.append(int(current))
    if len(digits) < 2:
        return None
    return digits[0], digits[1]


def _credential_is_private(definition: ProfileDefinition) -> tuple[bool, str]:
    path = SECRET_ROOT / definition.secret_name
    if not path.is_file():
        return False, "credential_missing"
    if path.is_symlink():
        return False, "credential_not_a_regular_file"
    if path.stat().st_mode & 0o077:
        return False, "credential_permissions_too_open"
    if not path.read_text(encoding="utf-8", errors="replace").strip():
        return False, "credential_empty"
    return True, ""


def _run(argv: tuple[str, ...], *, timeout: int = PROBE_TIMEOUT_SECONDS) -> tuple[int, str]:
    """Invoke a CLI with an explicit argv, no shell, and a scrubbed environment.

    `shell=False` is not a detail: the snapshot contains project text, and a
    shell would turn any of it into an injection surface.
    """

    environment = {
        "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.getenv("PROJECT_ANALYST_HOME", "/tmp/project-analyst"),
        "NO_COLOR": "1",
        # Provider CLIs that self-update would silently leave the pinned range.
        "CI": "1",
    }
    try:
        completed = subprocess.run(  # noqa: S603 - explicit argv, shell=False, scrubbed env
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
            shell=False,
            check=False,
        )
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    return completed.returncode, f"{completed.stdout}\n{completed.stderr}".strip()


def evaluate(definition: ProfileDefinition) -> ProfileStatus:
    """Decide whether one profile is selectable, and say why when it is not."""

    def refuse(reason: str, version: str = "") -> ProfileStatus:
        return ProfileStatus(
            id=definition.id,
            command=definition.command,
            ready=False,
            version=version,
            reason=reason,
        )

    if shutil.which(definition.command) is None:
        return refuse("cli_not_installed")

    code, output = _run((definition.command, *definition.version_argv))
    if code == 124:
        return refuse("cli_probe_timed_out")
    if code != 0:
        return refuse("cli_probe_failed")

    parsed = _parse_version(output)
    if parsed is None:
        return refuse("cli_version_unreadable")
    printed = f"{parsed[0]}.{parsed[1]}"
    if parsed < definition.minimum_version or parsed >= definition.below_version:
        return refuse("cli_version_outside_pinned_range", printed)

    credential_ok, credential_reason = _credential_is_private(definition)
    if not credential_ok:
        return refuse(credential_reason, printed)

    return ProfileStatus(id=definition.id, command=definition.command, ready=True, version=printed)


def discover() -> list[ProfileStatus]:
    """Every profile with its current readiness, ready or not.

    Unready profiles are still listed. Hiding them would leave an operator
    looking at an empty selector with no way to tell whether the CLI is missing,
    the version drifted, or the credential was never mounted.
    """

    return [evaluate(definition) for definition in PROFILES]
