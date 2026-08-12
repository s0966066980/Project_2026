"""Project analysis as coordination, not execution.

The UI API side of the Project Core Brain reads allowlisted evidence, hands it
across a process boundary, and keeps one report. These tests hold that shape:
what the snapshot may contain, what happens when the sidecar refuses, and the
two ways the report store must behave when a rescan fails.

The strongest assertions here are absences — no provider call, no shell, no
second provider after a failure — because those are what the old in-process
scaffold did and what the sidecar boundary exists to prevent.
"""

import ast
import asyncio
import json
import urllib.error
from pathlib import Path

import pytest

from project_analysis import report_store, sidecar_client, snapshot
from services import project_brain_service

pytestmark = [pytest.mark.slow]
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(relative_path: str) -> set[str]:
    """Top-level module names a file actually imports.

    Parsed rather than grepped: prose that names `subprocess` while explaining
    why it is absent must not fail the check that it is absent.
    """

    tree = ast.parse((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def _called_attributes(relative_path: str) -> set[str]:
    """Dotted names appearing in call position, e.g. `os.system`."""

    tree = ast.parse((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name):
                called.add(f"{value.id}.{node.func.attr}")
    return called


# --- Snapshot -----------------------------------------------------------------


def test_the_snapshot_carries_only_allowlisted_evidence():
    built = snapshot.build_snapshot(environment="test")

    assert built.payload["snapshot_version"] == "1"
    assert built.payload["evidence"], "the default set must resolve to something"
    for item in built.payload["evidence"]:
        assert set(item) == {"path", "size_bytes", "text"}


def test_a_refused_path_is_dropped_and_recorded_rather_than_read():
    built = snapshot.build_snapshot(
        environment="test",
        evidence_paths=("CONTEXT.md", "UI_API/.env", "../../etc/passwd"),
    )

    paths = {item["path"] for item in built.payload["evidence"]}
    assert paths == {"CONTEXT.md"}
    skipped = {entry["path"]: entry["reason"] for entry in built.skipped}
    assert set(skipped) == {"UI_API/.env", "../../etc/passwd"}
    assert all(reason.startswith("evidence_not_allowed:") for reason in skipped.values())


def test_skipped_evidence_never_crosses_to_the_sidecar():
    """The sidecar validates with extra="forbid"; diagnostics stay local."""

    built = snapshot.build_snapshot(environment="test", evidence_paths=("UI_API/.env",))
    assert "skipped" not in built.payload


def test_the_snapshot_names_the_revision_baked_into_the_build(monkeypatch):
    monkeypatch.setenv("APP_GIT_REVISION", "2d9ff98")
    assert snapshot.build_snapshot(environment="test").payload["git_revision"] == "2d9ff98"


@pytest.mark.parametrize("value", ["", "   ", "not a revision", "x" * 65, "abc;rm -rf /"])
def test_an_unusable_revision_reads_as_unknown_rather_than_being_guessed(monkeypatch, value):
    """A report that cannot name its revision is useful; one that guesses is not."""

    monkeypatch.setenv("APP_GIT_REVISION", value)
    assert snapshot.build_snapshot(environment="test").payload["git_revision"] == "unknown"


def test_the_snapshot_never_shells_out_for_the_revision():
    """The runtime image has no Git and no repository.

    Shelling out answered `unknown` every time, which is the kind of always-on
    fallback that reads as a working feature. It is now a build argument, which
    also keeps subprocess out of the UI API process entirely (ADR-0034).
    """

    path = "UI_API/backend/project_analysis/snapshot.py"
    assert "subprocess" not in _imported_modules(path)
    assert not (_called_attributes(path) & {"os.system", "os.popen", "subprocess.run", "subprocess.Popen"})


def test_the_revision_is_baked_in_at_build_time():
    dockerfile = (REPOSITORY_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG APP_GIT_REVISION" in dockerfile
    assert "ENV APP_GIT_REVISION=${APP_GIT_REVISION}" in dockerfile


def test_readiness_is_a_supplied_projection_not_a_settings_dump():
    built = snapshot.build_snapshot(environment="test", readiness={"ready": True})
    assert built.payload["readiness"] == {"ready": True}

    text = json.dumps(built.payload)
    for leaked in ("POSTGRES_PASSWORD", "ADMIN_MEMBER_REF_SECRET", "NVIDIA_API_KEY"):
        assert f'"{leaked}"' not in text or "example" in text.lower()


def test_the_snapshot_is_bounded_by_file_count():
    many = tuple(f"docs/adr/{index:04d}-nope.md" for index in range(200))
    built = snapshot.build_snapshot(environment="test", evidence_paths=many)
    assert len(built.payload["evidence"]) + len(built.skipped) <= snapshot.MAX_SNAPSHOT_FILES


# --- The sidecar boundary -----------------------------------------------------


def test_the_ui_api_process_no_longer_executes_a_provider():
    """The scaffold called the LLM gateway on a worker thread. That path is gone."""

    path = "UI_API/backend/services/project_brain_service.py"
    imported = _imported_modules(path)
    assert "subprocess" not in imported
    assert not (imported & {"llm_gateway_service", "models"})

    source = (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    referenced |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in ("llm_gateway_service", "LLMRequest", "to_thread", "generate"):
        assert forbidden not in referenced, f"{forbidden} must not return to the UI API process"


def test_analysis_failure_marks_the_previous_report_stale_and_never_retries_elsewhere(monkeypatch, tmp_path):
    monkeypatch.setattr(report_store, "_report_path", lambda: str(tmp_path / "latest.json"))
    report_store.replace({"profile": "codex", "findings": []})

    attempted: list[str] = []

    def refuse(*, profile, snapshot):
        attempted.append(profile)
        raise sidecar_client.SidecarUnavailable("profile_not_ready:credential_missing")

    monkeypatch.setattr(sidecar_client, "analyze", refuse)

    with pytest.raises(sidecar_client.SidecarUnavailable, match="credential_missing"):
        asyncio.run(project_brain_service.analyze("codex"))

    assert attempted == ["codex"], "a failed profile must not be retried against another one"
    kept = report_store.load()
    assert kept["status"] == "stale"
    assert kept["stale_reason"] == "profile_not_ready:credential_missing"
    assert kept["result"]["profile"] == "codex", "the previous report must survive a failed rescan"


@pytest.mark.parametrize(
    ("raised_error", "expected_reason"),
    [
        (urllib.error.URLError("connection refused to 10.0.0.5:7900"), "sidecar_unreachable"),
        (TimeoutError("timed out after 330s on 10.0.0.5"), "sidecar_timed_out"),
        (OSError("host 10.0.0.5 is down"), "sidecar_response_unreadable"),
    ],
)
def test_a_failing_sidecar_becomes_a_bounded_reason_not_a_stack_trace(monkeypatch, raised_error, expected_reason):
    """Patched at the socket, so the real translation runs rather than the test's."""

    def explode(request, timeout=None):
        raise raised_error

    monkeypatch.setattr(sidecar_client.urllib.request, "urlopen", explode)

    with pytest.raises(sidecar_client.SidecarUnavailable) as raised:
        sidecar_client.profiles()

    assert str(raised.value) == expected_reason
    assert "10.0.0.5" not in str(raised.value)


def test_a_sidecar_rejection_surfaces_its_reason_code_but_not_its_body(monkeypatch):
    """The sidecar's codes are already bounded; anything else becomes generic."""

    class Rejection(urllib.error.HTTPError):
        def __init__(self, body: str):
            super().__init__("http://project-analyst:7900/analyze", 409, "Conflict", {}, None)
            self._body = body.encode("utf-8")

        def read(self):
            return self._body

    def reject_with(body):
        def explode(request, timeout=None):
            raise Rejection(body)

        return explode

    monkeypatch.setattr(
        sidecar_client.urllib.request,
        "urlopen",
        reject_with(json.dumps({"detail": "profile_not_ready:credential_missing"})),
    )
    with pytest.raises(sidecar_client.SidecarUnavailable) as bounded:
        sidecar_client.profiles()
    assert str(bounded.value) == "profile_not_ready:credential_missing"

    monkeypatch.setattr(
        sidecar_client.urllib.request,
        "urlopen",
        reject_with(json.dumps({"detail": "Traceback:\n  File /run/secrets/codex\n" + "x" * 500})),
    )
    with pytest.raises(sidecar_client.SidecarUnavailable) as generic:
        sidecar_client.profiles()
    assert str(generic.value) == "sidecar_rejected_request"


def test_unready_profiles_are_reported_with_their_reason(monkeypatch):
    monkeypatch.setattr(
        sidecar_client,
        "profiles",
        lambda: [{"id": "codex", "ready": False, "reason": "credential_missing"}],
    )
    models = project_brain_service.ready_models()
    assert models[0]["ready"] is False
    assert models[0]["reason"] == "credential_missing"


# --- The report store ---------------------------------------------------------


def test_a_successful_rescan_replaces_and_deletes_the_previous_report(monkeypatch, tmp_path):
    monkeypatch.setattr(report_store, "_report_path", lambda: str(tmp_path / "latest.json"))

    report_store.replace({"profile": "codex", "findings": [{"severity": "warning", "title": "old"}]})
    report_store.replace({"profile": "claude", "findings": [{"severity": "healthy", "title": "new"}]})

    current = report_store.load()
    assert current["status"] == "current"
    assert current["result"]["profile"] == "claude"
    assert "old" not in json.dumps(current), "only the latest report is retained"
    assert list(tmp_path.iterdir()) == [tmp_path / "latest.json"], "no temporary file survives"


def test_replacement_leaves_no_partially_written_report(monkeypatch, tmp_path):
    """`os.replace` is a rename: a reader sees the old report or the new one."""

    path = tmp_path / "latest.json"
    monkeypatch.setattr(report_store, "_report_path", lambda: str(path))
    report_store.replace({"profile": "codex", "findings": []})

    with pytest.raises(ValueError, match="too_large"):
        report_store.replace({"profile": "codex", "detail": "x" * (report_store.MAX_REPORT_BYTES + 1)})

    survived = report_store.load()
    assert survived["result"]["profile"] == "codex"
    assert not (tmp_path / "latest.json.tmp").exists()


def test_marking_stale_without_a_previous_report_is_a_no_op(monkeypatch, tmp_path):
    monkeypatch.setattr(report_store, "_report_path", lambda: str(tmp_path / "latest.json"))
    assert report_store.mark_stale("sidecar_unreachable") is None


def test_a_corrupt_report_reads_as_absent_not_as_partial(monkeypatch, tmp_path):
    path = tmp_path / "latest.json"
    path.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(report_store, "_report_path", lambda: str(path))
    assert report_store.load() is None


def test_a_stale_reason_cannot_grow_into_a_provider_error_body(monkeypatch, tmp_path):
    monkeypatch.setattr(report_store, "_report_path", lambda: str(tmp_path / "latest.json"))
    report_store.replace({"profile": "codex", "findings": []})
    report_store.mark_stale("x" * 500)
    assert len(report_store.load()["stale_reason"]) <= 120


# --- The proposal endpoint ----------------------------------------------------


def test_the_in_process_proposal_generator_is_deleted_not_disabled():
    """It ran a provider inside the UI API process and called the output a proposal."""

    source = (REPOSITORY_ROOT / "UI_API" / "backend" / "services" / "project_brain_service.py").read_text(
        encoding="utf-8"
    )
    assert "def propose" not in source
    assert "proposal_kind_not_allowed" not in source
    assert "docs/proposals/" not in source
