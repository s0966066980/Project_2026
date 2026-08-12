"""A proposal produces a patch and changes nothing.

The properties under test are all negative, because a proposal workflow is
defined by what it cannot do: reach outside its module, edit a file that
already exists, commit, push, touch the active workspace, or leave a worktree
behind.

These run against a real Git repository built in `tmp_path`, not a mock. A
mocked clone would prove the code calls `git`, which is not the claim; the
claim is that the source tree is byte-identical afterwards.

There is no skip when git is absent. The tests that would skip are exactly the
ones that prove the isolation, so the test image installs git instead.
"""

import subprocess
from pathlib import Path

import pytest
from project_analyst import proposer

pytestmark = [pytest.mark.slow]


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(cwd),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@invalid",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@invalid",
        },
    )
    return result.stdout.strip()


@pytest.fixture()
def source(tmp_path, monkeypatch) -> Path:
    """A small real repository standing in for the project."""

    root = tmp_path / "source"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "existing.md").write_text("original\n", encoding="utf-8")
    (root / "extensions").mkdir()
    (root / "extensions" / "taken").mkdir()
    (root / "extensions" / "taken" / "README.md").write_text("already here\n", encoding="utf-8")

    _git("init", "--initial-branch=main", cwd=root)
    _git("add", "-A", cwd=root)
    _git("commit", "-m", "initial", cwd=root)

    monkeypatch.setattr(proposer, "SOURCE_ROOT", root)
    monkeypatch.setattr(proposer, "SCRATCH_ROOT", tmp_path / "scratch")
    return root


def _revision(source: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=source)


def _tree_fingerprint(root: Path) -> list[tuple[str, int, bytes]]:
    """Everything about the source tree that a proposal must not change."""

    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries.append((str(path.relative_to(root)), path.stat().st_size, path.read_bytes()))
    return entries


# --- Path confinement, decided before any filesystem work -------------------


@pytest.mark.parametrize(
    ("kind", "name", "filename", "rule"),
    [
        ("document", "note", "../../etc/passwd", "path_escape"),
        ("document", "note", "/etc/passwd", "absolute_filename"),
        ("document", "note", "sub/dir/note.md", "document_must_be_a_single_file"),
        ("document", "note", "note.py", "document_must_be_markdown"),
        ("extension", "queue", "../../../UI_API/config.py", "path_escape"),
        ("extension", "queue", ".git/config", "path_escape"),
        ("extension", "queue", "~/.ssh/id_rsa", "path_escape"),
        ("extension", "queue", "run.sh", "file_type"),
        ("extension", "queue", "weights.bin", "file_type"),
        ("migration", "queue", "x.py", "kind_not_allowed"),
        ("extension", "../escape", "x.py", "name_not_allowed"),
        ("extension", "UI_API", "x.py", "name_not_allowed"),
        ("extension", "a", "x.py", "name_not_allowed"),
        ("extension", "", "x.py", "name_not_allowed"),
    ],
)
def test_a_proposal_cannot_name_a_target_outside_its_module(kind, name, filename, rule):
    with pytest.raises(proposer.ProposalRefused, match=rule):
        proposer.target_path(kind, name, filename)


def test_allowed_targets_land_only_in_the_two_permitted_roots():
    assert proposer.target_path("document", "queue-display", "queue-display.md") == "docs/proposals/queue-display.md"
    assert proposer.target_path("extension", "queue-display", "app.py") == "extensions/queue-display/app.py"
    assert (
        proposer.target_path("extension", "queue-display", "tests/test_app.py")
        == "extensions/queue-display/tests/test_app.py"
    )


@pytest.mark.parametrize("revision", ["", "main", "HEAD", "origin/main", "abc", "x" * 65, "../../etc"])
def test_a_proposal_must_name_an_explicit_commit_not_a_branch(revision):
    """A branch would let the tree move under a proposal that claims to describe it."""

    with pytest.raises(proposer.ProposalRefused, match="revision_not_a_commit_id"):
        proposer.create_proposal(revision=revision, kind="document", name="note", files={"note.md": "x"})


# --- The active workspace is untouched --------------------------------------


def test_a_proposal_produces_a_patch_and_changes_nothing_in_the_source(source):
    before = _tree_fingerprint(source)

    proposal = proposer.create_proposal(
        revision=_revision(source),
        kind="document",
        name="queue-display",
        files={"queue-display.md": "# Queue display\n\nA proposal.\n"},
    )

    assert proposal.applied is False
    assert proposal.files == ["docs/proposals/queue-display.md"]
    assert "docs/proposals/queue-display.md" in proposal.patch
    assert "A proposal." in proposal.patch
    assert _tree_fingerprint(source) == before, "the active workspace must be byte-identical afterwards"
    assert not (source / "docs" / "proposals").exists()


def test_the_proposal_does_not_commit_switch_or_push(source):
    head_before = _revision(source)
    branch_before = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=source)
    log_before = _git("log", "--oneline", cwd=source)

    proposer.create_proposal(
        revision=head_before,
        kind="extension",
        name="queue-display",
        files={"app.py": "VALUE = 1\n"},
    )

    assert _revision(source) == head_before
    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=source) == branch_before
    assert _git("log", "--oneline", cwd=source) == log_before
    assert _git("status", "--porcelain", cwd=source) == "", "the source working tree must stay clean"


def test_the_isolated_worktree_does_not_outlive_the_request(source, tmp_path):
    proposer.create_proposal(
        revision=_revision(source),
        kind="extension",
        name="queue-display",
        files={"app.py": "VALUE = 1\n"},
    )

    scratch = tmp_path / "scratch"
    leftovers = [path for path in scratch.iterdir()] if scratch.exists() else []
    assert leftovers == [], "rejection and expiry are not separate cleanup paths that could be forgotten"


def test_a_refused_proposal_leaves_no_worktree_behind(source, tmp_path):
    with pytest.raises(proposer.ProposalRefused):
        proposer.create_proposal(
            revision=_revision(source),
            kind="extension",
            name="queue-display",
            files={"../../UI_API/config.py": "BREAK = True\n"},
        )

    scratch = tmp_path / "scratch"
    assert not scratch.exists() or list(scratch.iterdir()) == []


# --- Additions only ----------------------------------------------------------


def test_a_proposal_cannot_modify_a_file_that_already_exists(source):
    with pytest.raises(proposer.ProposalRefused, match="would_modify_an_existing_file"):
        proposer.create_proposal(
            revision=_revision(source),
            kind="extension",
            name="taken",
            files={"README.md": "rewritten\n"},
        )

    assert (source / "extensions" / "taken" / "README.md").read_text(encoding="utf-8") == "already here\n"


def test_a_proposal_cannot_reach_an_unknown_revision(source):
    with pytest.raises(proposer.ProposalRefused, match="revision_not_found"):
        proposer.create_proposal(
            revision="0" * 40,
            kind="document",
            name="note",
            files={"note.md": "x\n"},
        )


# --- Bounds ------------------------------------------------------------------


def test_a_proposal_is_bounded_by_file_count(source):
    files = {f"module{index}.py": "x\n" for index in range(proposer.MAX_FILES + 1)}
    with pytest.raises(proposer.ProposalRefused, match="too_many_files"):
        proposer.create_proposal(revision=_revision(source), kind="extension", name="big", files=files)


def test_a_proposal_is_bounded_by_file_size(source):
    oversized = "x" * (proposer.MAX_FILE_BYTES + 1)
    with pytest.raises(proposer.ProposalRefused, match="file_too_large"):
        proposer.create_proposal(revision=_revision(source), kind="extension", name="big", files={"app.py": oversized})


def test_an_empty_proposal_is_refused(source):
    with pytest.raises(proposer.ProposalRefused, match="no_files_proposed"):
        proposer.create_proposal(revision=_revision(source), kind="document", name="note", files={})


# --- Verification ------------------------------------------------------------


def test_an_extension_with_its_own_tests_is_verified_inside_the_clone(source):
    proposal = proposer.create_proposal(
        revision=_revision(source),
        kind="extension",
        name="queue-display",
        files={
            "app.py": "def total(values):\n    return sum(values)\n",
            "tests/test_app.py": (
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
                "from app import total\n"
                "\n"
                "def test_total():\n"
                "    assert total([1, 2]) == 3\n"
            ),
        },
    )

    assert proposal.verification.ran is True
    assert proposal.verification.passed is True


def test_a_failing_extension_reports_failure_rather_than_being_dropped(source):
    proposal = proposer.create_proposal(
        revision=_revision(source),
        kind="extension",
        name="queue-display",
        files={
            "app.py": "def total(values):\n    return 0\n",
            "tests/test_app.py": (
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
                "from app import total\n"
                "\n"
                "def test_total():\n"
                "    assert total([1, 2]) == 3\n"
            ),
        },
    )

    assert proposal.verification.ran is True
    assert proposal.verification.passed is False


def test_an_extension_without_tests_says_so_rather_than_claiming_it_passed(source):
    proposal = proposer.create_proposal(
        revision=_revision(source),
        kind="extension",
        name="queue-display",
        files={"app.py": "VALUE = 1\n"},
    )

    assert proposal.verification.ran is False
    assert proposal.verification.passed is False
    assert proposal.verification.summary == "no_tests_supplied"


def test_a_document_proposal_makes_no_verification_claim(source):
    proposal = proposer.create_proposal(
        revision=_revision(source), kind="document", name="note", files={"note.md": "# Note\n"}
    )
    assert proposal.verification.ran is False
    assert proposal.verification.passed is False


# --- Injection surface --------------------------------------------------------


def test_the_workflow_never_invokes_a_shell():
    """Proposal content is provider-generated text. A shell would make it executable."""

    source_text = (Path(proposer.__file__)).read_text(encoding="utf-8")
    assert "shell=False" in source_text
    assert "shell=True" not in source_text
    assert "os.system" not in source_text
