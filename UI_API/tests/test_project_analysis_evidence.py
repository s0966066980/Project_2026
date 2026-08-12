"""What project analysis may read, and everything it may not.

ADR-0034 draws this boundary in prose. These tests are where it is enforced:
each refusal below is a path that a provider running against this repository
must never receive, and each acceptance is evidence the capability is supposed
to work from.

The refusals matter more than the acceptances. A snapshot builder that silently
returns nothing for a denied path looks the same as one that reads it, so every
denial asserts the specific rule that stopped it.
"""

from pathlib import Path

import pytest

from project_analysis import evidence

# --- Accepted evidence ------------------------------------------------------


pytestmark = [pytest.mark.architecture]


@pytest.mark.parametrize(
    "path",
    [
        "UI_API/backend/project_analysis/evidence.py",
        "UI_API/tests/test_project_analysis_evidence.py",
        "UI_API/frontend/kiosk/voiceDialogueReducer.js",
        "docs/adr/0034-bound-the-project-core-brain-to-read-only-evidence.md",
        "docker/compose.pilot.yaml",
        "CONTEXT.md",
        "AGENTS.md",
    ],
)
def test_allowlisted_project_evidence_is_readable(path):
    result = evidence.read_evidence(path)
    assert result.path == path
    assert result.text
    assert result.size_bytes > 0


def test_listing_stays_inside_the_allowlist():
    found = evidence.list_evidence("UI_API/backend/project_analysis")
    assert "UI_API/backend/project_analysis/evidence.py" in found
    assert all(evidence.is_allowed(path) for path in found)


def test_listing_is_bounded():
    assert len(evidence.list_evidence("UI_API/backend", limit=5)) <= 5


# --- Credentials and configuration -----------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "UI_API/.env",
        "UI_API/.env.local",
        "docker/.env.example",
        "config/profiles/local-pilot.env.example",
        "UI_API/backend/secrets.py",
        "docs/my-credentials.md",
        "docker/database_password.txt",
        "tools/api_token.py",
        "UI_API/backend/id_rsa",
        "docker/server.pem",
        "docker/server.key",
    ],
)
def test_credential_bearing_paths_are_refused(path):
    with pytest.raises(evidence.EvidenceNotAllowed) as raised:
        evidence.read_evidence(path)
    assert str(raised.value).startswith("evidence_not_allowed:")


def test_a_credential_name_is_refused_even_inside_an_allowed_prefix(tmp_path):
    # The file need not exist: the name is refused before the disk is touched.
    with pytest.raises(evidence.EvidenceNotAllowed, match="credential_name"):
        evidence.read_evidence("UI_API/backend/nvidia_api_token.py")


@pytest.mark.parametrize(
    ("path", "fragment"),
    [
        ("docs/.env.md", ".env"),
        ("docs/dotenv-secret.md", "secret"),
        ("docs/reset-password.md", "password"),
        ("docs/refresh-token.md", "token"),
        ("docs/service-credential.md", "credential"),
        ("docs/passwd.md", "passwd"),
        ("UI_API/backend/id_rsa.py", "id_rsa"),
        ("UI_API/backend/id_ed25519.py", "id_ed25519"),
    ],
)
def test_each_credential_name_fragment_is_load_bearing_on_its_own(path, fragment):
    """Every fragment must be the only thing refusing at least one path.

    Without this, dropping a fragment from the list changes nothing that any
    test observes, because another rule happens to catch the paths it was
    protecting — and the list quietly stops meaning anything.
    """

    assert fragment in evidence.DENIED_NAME_FRAGMENTS
    with pytest.raises(evidence.EvidenceNotAllowed, match="credential_name"):
        evidence.read_evidence(path)


# --- Escaping the repository ------------------------------------------------


@pytest.mark.parametrize(
    ("path", "rule"),
    [
        ("/etc/passwd", "absolute_path"),
        ("/home/oliver/.ssh/id_rsa", "absolute_path"),
        ("../../etc/shadow", "parent_traversal"),
        ("UI_API/backend/../../../etc/hosts", "parent_traversal"),
        ("~/.config/project-2026/pilot.env", "home_reference"),
        ("~", "home_reference"),
        ("", "empty_path"),
        ("UI_API/backend/evidence\x00.py", "null_byte"),
    ],
)
def test_paths_that_leave_the_project_are_refused(path, rule):
    with pytest.raises(evidence.EvidenceNotAllowed, match=rule):
        evidence.read_evidence(path)


def test_backslash_separators_cannot_smuggle_a_traversal():
    with pytest.raises(evidence.EvidenceNotAllowed, match="parent_traversal"):
        evidence.read_evidence(r"UI_API\backend\..\..\..\etc\passwd")


def test_a_symlink_component_is_refused(tmp_path, monkeypatch):
    """A symlink inside the repository can point anywhere on the host.

    Built against a stand-in repository root rather than the real one. A test
    that plants a symlink in the source tree fails on a read-only checkout and
    leaves debris if the process dies — and this project's own proposal
    workflow refuses exactly that kind of write.
    """

    fake_root = tmp_path / "repo"
    inside = fake_root / "UI_API" / "backend" / "project_analysis"
    inside.mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("secret", encoding="utf-8")
    (inside / "escape_probe.py").symlink_to(outside)

    monkeypatch.setattr(evidence, "REPOSITORY_ROOT", fake_root)
    with pytest.raises(evidence.EvidenceNotAllowed, match="symlink_component"):
        evidence.read_evidence("UI_API/backend/project_analysis/escape_probe.py")


def test_a_symlinked_parent_directory_is_refused(tmp_path, monkeypatch):
    """The walk checks every component, not just the final one."""

    fake_root = tmp_path / "repo"
    (fake_root / "UI_API" / "backend").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "evidence.py").write_text("secret", encoding="utf-8")
    (fake_root / "UI_API" / "backend" / "project_analysis").symlink_to(elsewhere)

    monkeypatch.setattr(evidence, "REPOSITORY_ROOT", fake_root)
    with pytest.raises(evidence.EvidenceNotAllowed, match="symlink_component"):
        evidence.read_evidence("UI_API/backend/project_analysis/evidence.py")


# --- Runtime state, customer data and generated output ----------------------


@pytest.mark.parametrize(
    "path",
    [
        "UI_API/learning_data/settings.json",
        "UI_API/learning_data/emotion_analysis_records.json",
        "UI_API/runtime_data/objects/receipt.png",
        "UI_API/frontend/node_modules/vite/package.json",
        "UI_API/frontend/dist/kiosk/app.js",
        "UI_API/frontend/test-results/trace.zip",
        "R1-Omni/models/R1-Omni-0.5B/config.json",
        ".git/config",
        "UI_API/backend/__pycache__/config.cpython-310.pyc",
    ],
)
def test_runtime_state_and_generated_output_are_refused(path):
    with pytest.raises(evidence.EvidenceNotAllowed):
        evidence.read_evidence(path)


@pytest.mark.parametrize(
    "path",
    [
        "docs/recording.wav",
        "docs/camera-frame.png",
        "UI_API/backend/model.bin",
        "UI_API/backend/data.db",
        "docs/archive.zip",
    ],
)
def test_media_and_binary_evidence_is_refused_by_type(path):
    with pytest.raises(evidence.EvidenceNotAllowed, match="file_type"):
        evidence.read_evidence(path)


# --- Boundaries of the reader itself ---------------------------------------


def test_a_directory_is_not_evidence():
    with pytest.raises(evidence.EvidenceNotAllowed, match="not_a_regular_file"):
        evidence.read_evidence("UI_API/backend/project_analysis")


def test_a_missing_allowlisted_file_reports_not_found_without_a_host_path():
    with pytest.raises(evidence.EvidenceNotAllowed) as raised:
        evidence.read_evidence("UI_API/backend/project_analysis/no_such_file.py")
    message = str(raised.value)
    assert message == "evidence_not_allowed:not_found"
    assert str(evidence.REPOSITORY_ROOT) not in message


def test_an_oversized_file_is_refused(monkeypatch):
    monkeypatch.setattr(evidence, "MAX_EVIDENCE_BYTES", 10)
    with pytest.raises(evidence.EvidenceNotAllowed, match="too_large"):
        evidence.read_evidence("CONTEXT.md")


def test_refusal_messages_never_disclose_the_resolved_host_path():
    for path in ("/etc/passwd", "../../etc/shadow", "UI_API/.env"):
        try:
            evidence.read_evidence(path)
        except evidence.EvidenceNotAllowed as error:
            assert str(Path.home()) not in str(error)
            assert "/etc" not in str(error)


@pytest.mark.parametrize(
    "path",
    [
        "UI_API/backend/__pycache__/config.cpython-310.py",
        "UI_API/backend/build/generated.py",
        "docs/node_modules/readme.md",
        "docker/dist/compose.yaml",
        "UI_API/tests/coverage/report.md",
    ],
)
def test_a_denied_directory_inside_an_allowed_prefix_is_the_rule_that_refuses(path):
    """Generated output under an allowed prefix passes every other check.

    Right prefix, allowed suffix, innocent name — only the denied-directory
    rule stops these, so only this test keeps that rule honest.
    """

    with pytest.raises(evidence.EvidenceNotAllowed, match="denied_directory"):
        evidence.read_evidence(path)


@pytest.mark.parametrize(
    "path",
    [
        "R1-Omni/README.md",
        "R1-Omni/inference.py",
        "config/profiles/notes.md",
        "UI_API/requirements-ai.txt",
        "UI_API/frontend/package.json",
    ],
)
def test_a_project_path_outside_every_allowlisted_prefix_is_refused(path):
    """Real repository paths that simply were not allowlisted.

    Nothing about the name, suffix or directory is suspicious; they are refused
    because the allowlist is the whole permission, which is the property that
    makes it survive someone adding a directory.
    """

    with pytest.raises(evidence.EvidenceNotAllowed, match="outside_allowlist"):
        evidence.read_evidence(path)


def test_no_allowlisted_prefix_reaches_into_a_denied_directory():
    """The two lists must not contradict each other.

    A prefix such as `UI_API/learning_data` would currently still be refused by
    the denied-directory rule, so nothing observable breaks — which is exactly
    why it needs asserting here rather than being left to the layer below.
    """

    for prefix in evidence.ALLOWED_PREFIXES:
        parts = set(prefix.split("/"))
        assert not (parts & evidence.DENIED_PATH_PARTS), f"{prefix} allowlists a denied directory"


def test_the_repository_boundary_backstop_refuses_an_escaping_resolution():
    """The last-resort check, exercised on its own.

    Nothing reaches it through `read_evidence` because absolute paths,
    traversal and symlinks are refused earlier. That makes it defence in depth
    rather than dead code, and it stays defence in depth only while something
    proves it still rejects.
    """

    from pathlib import PurePosixPath

    with pytest.raises(evidence.EvidenceNotAllowed, match="outside_repository"):
        evidence._resolved_inside_repository(PurePosixPath("../.."))


def test_the_evidence_gate_exposes_no_write_or_execute_entry_point():
    """Reading is the whole surface. ADR-0034 gives this capability nothing else."""

    public = {name for name in dir(evidence) if not name.startswith("_")}
    forbidden = {"write", "write_evidence", "run", "execute", "shell", "delete", "remove", "apply"}
    assert not (public & forbidden)
