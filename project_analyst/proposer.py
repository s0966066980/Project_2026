"""Project Change Proposals: a patch, never an applied change.

[ADR-0039](../docs/adr/0039-generate-project-change-proposals-without-applying-them.md)
gives this workflow no repository write authority. It creates one disposable
isolated worktree at an explicit Git revision, writes only the files it is
allowed to add, produces a patch, runs only its allowlisted verification, and
returns. It cannot modify the active workspace, commit, switch a branch, push,
or open a pull request.
[ADR-0040](../docs/adr/0040-confine-non-core-proposals-to-new-isolated-modules.md)
narrows what it may add to documents under `docs/proposals/` and new Non-Core
Extension Modules under `extensions/<name>/`.

The isolation is a clone, not a `git worktree`. `git worktree add` writes
metadata into the source repository's `.git` directory; a clone reads the
source and writes nothing to it, which is what lets the source be mounted
read-only and makes "cannot modify the active workspace" a property of the
mount rather than a promise in code.

The clone lives only for the duration of one request and is removed in a
`finally`. That is stronger than retaining proposals and cleaning them up
later, and it makes ADR-0039's "rejected or expired proposals permanently
remove their isolated worktree and artifacts" true by construction.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SOURCE_ROOT = Path(os.getenv("PROPOSER_SOURCE_ROOT", "/srv/source"))
SCRATCH_ROOT = Path(os.getenv("PROPOSER_SCRATCH_ROOT", "/tmp/proposals"))

CLONE_TIMEOUT_SECONDS = 120
PATCH_TIMEOUT_SECONDS = 60
VERIFICATION_TIMEOUT_SECONDS = 300

MAX_FILES = 40
MAX_FILE_BYTES = 128 * 1024
MAX_PATCH_BYTES = 1024 * 1024

DOCUMENT_ROOT = "docs/proposals"
EXTENSION_ROOT = "extensions"

# An extension module name, not a path. Anything that could traverse, hide, or
# collide with an existing directory is refused before a file is written.
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")

ALLOWED_SUFFIXES = frozenset({".md", ".py", ".txt", ".toml", ".json", ".cfg", ".yaml", ".yml"})


class ProposalRefused(Exception):
    """The proposal asked for something outside what it may add.

    Every refusal is a rule name. A proposal that is refused has produced
    nothing: no file, no patch, and no surviving worktree.
    """


@dataclass(frozen=True)
class Verification:
    ran: bool
    passed: bool
    summary: str = ""


@dataclass(frozen=True)
class Proposal:
    revision: str
    kind: str
    name: str
    files: list[str] = field(default_factory=list)
    patch: str = ""
    verification: Verification = field(default_factory=lambda: Verification(ran=False, passed=False))
    applied: bool = False


def _refuse(rule: str) -> ProposalRefused:
    return ProposalRefused(f"proposal_refused:{rule}")


def _run(argv: list[str], *, cwd: Path, timeout: int) -> tuple[int, str]:
    """Explicit argv, no shell, scrubbed environment.

    The proposal request carries provider-generated text. A shell would make
    any of it executable.
    """

    environment = {
        "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(SCRATCH_ROOT),
        "GIT_TERMINAL_PROMPT": "0",
        # Nothing this workflow does may reach the network, and an accidental
        # fetch or push must fail rather than hang on credentials.
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "project-proposer",
        "GIT_AUTHOR_EMAIL": "proposer@invalid",
        "GIT_COMMITTER_NAME": "project-proposer",
        "GIT_COMMITTER_EMAIL": "proposer@invalid",
    }
    try:
        completed = subprocess.run(  # noqa: S603 - explicit argv, shell=False, scrubbed env
            argv,
            cwd=str(cwd),
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


def _validate_revision(revision: str) -> str:
    candidate = str(revision or "").strip()
    if not candidate or len(candidate) > 64 or not re.fullmatch(r"[0-9a-fA-F]{7,64}", candidate):
        raise _refuse("revision_not_a_commit_id")
    return candidate


def target_path(kind: str, name: str, filename: str) -> str:
    """The one place a proposal of this kind and name may write.

    Refusals happen here, before any filesystem work, so a proposal that tries
    to reach outside its module never gets as far as a worktree.
    """

    if kind not in {"document", "extension"}:
        raise _refuse("kind_not_allowed")
    if NAME_PATTERN.fullmatch(name or "") is None:
        raise _refuse("name_not_allowed")

    relative = str(filename or "").strip().replace("\\", "/")
    if not relative:
        raise _refuse("empty_filename")
    posix = PurePosixPath(relative)
    if posix.is_absolute():
        raise _refuse("absolute_filename")
    if any(part in {"..", "~", ".git"} or part.startswith("~") for part in posix.parts):
        raise _refuse("path_escape")
    if posix.suffix.lower() not in ALLOWED_SUFFIXES:
        raise _refuse("file_type")

    if kind == "document":
        # One flat Markdown file under docs/proposals/. A document proposal that
        # could create directories would be an extension wearing another name.
        if len(posix.parts) != 1:
            raise _refuse("document_must_be_a_single_file")
        if posix.suffix.lower() != ".md":
            raise _refuse("document_must_be_markdown")
        return f"{DOCUMENT_ROOT}/{posix.name}"
    return f"{EXTENSION_ROOT}/{name}/{posix.as_posix()}"


def _assert_new(workspace: Path, relative: str) -> None:
    """A proposal may add files. It may not edit one that already exists."""

    if (workspace / relative).exists():
        raise _refuse("would_modify_an_existing_file")


def _clone(revision: str, destination: Path) -> None:
    # `--no-hardlinks` copies objects instead of linking them into the source's
    # object store, so nothing the clone does can reach back. Sharing is off by
    # default and `--shared` takes no value, so it must not be passed at all.
    code, _ = _run(
        ["git", "clone", "--no-hardlinks", "--no-checkout", str(SOURCE_ROOT), str(destination)],
        cwd=SCRATCH_ROOT,
        timeout=CLONE_TIMEOUT_SECONDS,
    )
    if code == 127:
        raise _refuse("git_unavailable")
    if code == 124:
        raise _refuse("clone_timed_out")
    if code != 0:
        raise _refuse("clone_failed")

    # An explicit revision, never a branch name: a proposal describes one tree,
    # and a branch would let the tree move under it.
    code, _ = _run(["git", "checkout", "--detach", revision], cwd=destination, timeout=CLONE_TIMEOUT_SECONDS)
    if code != 0:
        raise _refuse("revision_not_found")


def _verify_extension(workspace: Path, name: str) -> Verification:
    """Run only the extension's own tests, inside the isolated clone.

    An extension can be verified without editing or running the current
    production system (ADR-0040), so this is the whole allowlist: one pytest
    invocation, scoped to the module's own directory, bounded in time.
    """

    tests = workspace / EXTENSION_ROOT / name / "tests"
    if not tests.is_dir():
        return Verification(ran=False, passed=False, summary="no_tests_supplied")

    code, output = _run(
        ["python", "-m", "pytest", f"{EXTENSION_ROOT}/{name}/tests", "-q"],
        cwd=workspace,
        timeout=VERIFICATION_TIMEOUT_SECONDS,
    )
    if code == 124:
        return Verification(ran=True, passed=False, summary="verification_timed_out")
    tail = output.strip().splitlines()[-1:] or [""]
    return Verification(ran=True, passed=code == 0, summary=tail[0][:200])


def create_proposal(*, revision: str, kind: str, name: str, files: dict[str, str]) -> Proposal:
    """Produce a patch for a proposed addition, and nothing else.

    `files` is content someone else generated. Generation is the analyst
    sidecar's job; confinement is this workflow's, and it applies the same way
    whatever produced the text.
    """

    checked_revision = _validate_revision(revision)
    if not files:
        raise _refuse("no_files_proposed")
    if len(files) > MAX_FILES:
        raise _refuse("too_many_files")

    targets: dict[str, str] = {}
    for filename, content in files.items():
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise _refuse("file_too_large")
        targets[target_path(kind, name, filename)] = content

    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="proposal-", dir=SCRATCH_ROOT))
    try:
        _clone(checked_revision, workspace)

        for relative, content in targets.items():
            _assert_new(workspace, relative)
            destination = workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")

        # Staged, never committed. `--cached` against the index is how the diff
        # can include files Git has not seen before without a commit existing.
        code, _ = _run(["git", "add", "--intent-to-add", "--", *targets], cwd=workspace, timeout=PATCH_TIMEOUT_SECONDS)
        if code != 0:
            raise _refuse("patch_staging_failed")
        code, patch = _run(["git", "diff"], cwd=workspace, timeout=PATCH_TIMEOUT_SECONDS)
        if code != 0:
            raise _refuse("patch_generation_failed")
        if len(patch.encode("utf-8")) > MAX_PATCH_BYTES:
            raise _refuse("patch_too_large")

        verification = (
            _verify_extension(workspace, name) if kind == "extension" else Verification(ran=False, passed=False)
        )

        return Proposal(
            revision=checked_revision,
            kind=kind,
            name=name,
            files=sorted(targets),
            patch=patch,
            verification=verification,
            applied=False,
        )
    finally:
        # The worktree does not outlive the request. Rejection and expiry are
        # therefore not separate cleanup paths that could be forgotten.
        shutil.rmtree(workspace, ignore_errors=True)
