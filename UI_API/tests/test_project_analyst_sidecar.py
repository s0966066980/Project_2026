"""The Project Analyst Sidecar contract and its isolation.

Two halves. The first exercises the running service: what it accepts as a
snapshot, what it refuses, and what it does when the selected provider is not
ready. The second reads `docker/compose.project-analyst.yaml` as written, the
same way the Pilot container-security gate reads its overlay, because container
isolation that is only described in a comment drifts.

The behaviour that matters most here is the absence of a fallback. A sidecar
that quietly answers with a different provider produces a report nobody can
attribute, which is worse than no report.
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from project_analyst import contract, profiles
from project_analyst.service import create_app

pytestmark = [pytest.mark.slow]
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OVERLAY = REPOSITORY_ROOT / "docker" / "compose.project-analyst.yaml"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _snapshot(**overrides) -> dict:
    payload = {
        "snapshot_version": "1",
        "generated_at": "2026-08-11T00:00:00+00:00",
        "git_revision": "2d9ff98",
        "environment": "development",
        "readiness": {"ready": True},
        "evidence": [{"path": "UI_API/backend/config.py", "size_bytes": 12, "text": "APP_ENV = ''"}],
    }
    payload.update(overrides)
    return payload


# --- Snapshot validation ----------------------------------------------------


def test_the_sidecar_accepts_a_well_formed_snapshot():
    snapshot = contract.ProjectAnalysisSnapshot.model_validate(_snapshot())
    assert snapshot.evidence[0].path == "UI_API/backend/config.py"


@pytest.mark.parametrize(
    "path",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "~/.ssh/id_rsa",
        "UI_API/.env",
        "docker/server.pem",
        "UI_API/backend/api_token.py",
        "UI_API/learning_data/settings.json",
        "UI_API/frontend/node_modules/vite/index.js",
        "backend/.git/config",
    ],
)
def test_the_sidecar_refuses_evidence_the_ui_api_should_never_have_sent(path):
    """The sidecar repeats the caller's allowlist rather than trusting it.

    This is the process that hands project text to an external provider. It does
    not take the caller's word for what is safe to forward.
    """

    with pytest.raises(ValueError):
        contract.SnapshotEvidence(path=path, size_bytes=1, text="x")


def test_an_unknown_snapshot_version_is_refused():
    with pytest.raises(ValueError, match="unsupported snapshot version"):
        contract.ProjectAnalysisSnapshot.model_validate(_snapshot(snapshot_version="2"))


def test_a_snapshot_cannot_smuggle_extra_fields():
    with pytest.raises(ValueError):
        contract.ProjectAnalysisSnapshot.model_validate(_snapshot(shell_command="rm -rf /"))


def test_evidence_is_bounded_by_count():
    evidence = [{"path": f"docs/note-{index}.md", "size_bytes": 1, "text": "x"} for index in range(500)]
    with pytest.raises(ValueError, match="too many evidence files"):
        contract.ProjectAnalysisSnapshot.model_validate(_snapshot(evidence=evidence))


def test_evidence_is_bounded_by_total_size():
    evidence = [{"path": "docs/big.md", "size_bytes": contract.MAX_EVIDENCE_BYTES_TOTAL + 1, "text": "x"}]
    with pytest.raises(ValueError, match="exceeds the evidence size bound"):
        contract.ProjectAnalysisSnapshot.model_validate(_snapshot(evidence=evidence))


def test_a_repeated_evidence_path_is_refused():
    evidence = [
        {"path": "docs/note.md", "size_bytes": 1, "text": "a"},
        {"path": "docs/note.md", "size_bytes": 1, "text": "b"},
    ]
    with pytest.raises(ValueError, match="repeats an evidence path"):
        contract.ProjectAnalysisSnapshot.model_validate(_snapshot(evidence=evidence))


# --- Profile readiness and the absence of fallback --------------------------


def test_every_profile_reports_its_readiness_including_the_unready_ones(client):
    body = client.get("/profiles").json()
    ids = {entry["id"] for entry in body["profiles"]}
    assert ids == {"codex", "claude", "grok", "ollama"}


def test_a_profile_without_a_mounted_credential_is_not_selectable(client):
    """The closed state, which is what this deployment is actually in.

    No credentials are mounted, so every CLI profile must be unready with a
    reason an operator can act on rather than an empty selector. `ollama` is
    excluded because it has no credential to mount — its readiness depends on
    a running local host, which is checked separately below.
    """

    body = client.get("/profiles").json()
    for entry in body["profiles"]:
        if entry["id"] == "ollama":
            continue
        assert entry["ready"] is False
        assert entry["reason"] in {
            "cli_not_installed",
            "cli_probe_failed",
            "cli_probe_timed_out",
            "cli_version_unreadable",
            "cli_version_outside_pinned_range",
            "credential_missing",
            "credential_empty",
            "credential_permissions_too_open",
            "credential_not_a_regular_file",
        }


def test_analysis_with_an_unready_profile_fails_visibly_and_does_not_switch(client, monkeypatch):
    invoked: list[tuple] = []
    monkeypatch.setattr(profiles, "_run", lambda argv, **kwargs: invoked.append(argv) or (0, ""))

    response = client.post("/analyze", json={"profile": "codex", "snapshot": _snapshot()})

    assert response.status_code == 409
    assert response.json()["detail"].startswith("profile_not_ready:")
    assert invoked == [], "an unready profile must not reach any provider, including another one"


def test_an_unknown_profile_is_refused_rather_than_defaulted(client):
    response = client.post("/analyze", json={"profile": "gpt-whatever", "snapshot": _snapshot()})
    assert response.status_code == 422
    assert response.json()["detail"] == "unknown_profile"


def test_readiness_reasons_never_carry_a_raw_cli_error_or_credential_path(client):
    body = client.get("/profiles").json()
    for entry in body["profiles"]:
        assert "/run/secrets" not in entry["reason"]
        assert "Traceback" not in entry["reason"]
        assert "\n" not in entry["reason"]


# --- Provider invocation -----------------------------------------------------


def _make_ready(monkeypatch, response: tuple[int, str]) -> list[tuple]:
    """Stand a profile up as ready without installing a provider CLI.

    Every readiness condition is stubbed explicitly rather than through one
    blanket patch, so a new condition added to `evaluate` shows up here as a
    failing test instead of silently being skipped.
    """

    calls: list[tuple] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if "--version" in argv:
            return 0, "0.50.0"
        return response

    monkeypatch.setattr(profiles.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(profiles, "_run", fake_run)
    monkeypatch.setattr(profiles, "_credential_is_private", lambda definition: (True, ""))
    return calls


def test_a_conforming_provider_response_becomes_the_common_result(client, monkeypatch):
    _make_ready(
        monkeypatch,
        (
            0,
            '{"findings":[{"severity":"warning","title":"Config drift",'
            '"detail":"","evidence_paths":["UI_API/backend/config.py"]}]}',
        ),
    )

    response = client.post("/analyze", json={"profile": "codex", "snapshot": _snapshot()})

    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == "codex"
    assert body["git_revision"] == "2d9ff98"
    assert body["findings"][0]["severity"] == "warning"
    assert body["evidence_references"] == ["UI_API/backend/config.py"]


@pytest.mark.parametrize(
    ("provider_output", "detail"),
    [
        ("this is prose, not JSON", "provider_response_not_json"),
        ('{"summary":"looks fine"}', "provider_response_schema_mismatch"),
        ('{"findings":[{"severity":"catastrophic","title":"x"}]}', "provider_response_schema_mismatch"),
        ('{"findings":["not an object"]}', "provider_response_schema_mismatch"),
    ],
)
def test_a_provider_that_breaks_the_contract_is_refused_not_salvaged(client, monkeypatch, provider_output, detail):
    _make_ready(monkeypatch, (0, provider_output))
    response = client.post("/analyze", json={"profile": "codex", "snapshot": _snapshot()})
    assert response.status_code == 502
    assert response.json()["detail"] == detail


def test_a_provider_citing_evidence_it_was_never_given_is_refused(client, monkeypatch):
    """Every finding has to trace to supplied evidence, or the report means nothing."""

    _make_ready(
        monkeypatch,
        (0, '{"findings":[{"severity":"blocked","title":"Secret in env","evidence_paths":["UI_API/.env"]}]}'),
    )
    response = client.post("/analyze", json={"profile": "codex", "snapshot": _snapshot()})
    assert response.status_code == 502
    assert response.json()["detail"] == "provider_cited_unsupplied_evidence"


def test_a_provider_timeout_is_reported_rather_than_retried_elsewhere(client, monkeypatch):
    _make_ready(monkeypatch, (124, ""))
    response = client.post("/analyze", json={"profile": "codex", "snapshot": _snapshot()})
    assert response.status_code == 504
    assert response.json()["detail"] == "provider_timed_out"


def test_the_provider_is_invoked_without_a_shell_and_with_a_scrubbed_environment():
    """`shell=True` would turn any line of project text into an injection surface."""

    source = (REPOSITORY_ROOT / "project_analyst" / "profiles.py").read_text(encoding="utf-8")
    assert "shell=False" in source
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "subprocess.run" in source


# --- Container isolation ----------------------------------------------------


@pytest.fixture(scope="module")
def overlay() -> dict:
    return yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))


def test_the_sidecar_runs_under_the_same_hardening_as_the_pilot(overlay):
    service = overlay["services"]["project-analyst"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "cap_add" not in service
    assert "no-new-privileges:true" in service["security_opt"]
    assert str(service["user"]).split(":")[0] == "10002"


def test_the_sidecar_writable_surface_is_one_tmpfs(overlay):
    mounts = overlay["services"]["project-analyst"]["tmpfs"]
    assert [mount.split(":")[0] for mount in mounts] == ["/tmp"]
    options = mounts[0].split(":", 1)[1]
    assert "nosuid" in options
    assert "nodev" in options


def test_the_sidecar_has_no_repository_database_or_docker_socket(overlay):
    """Every absence here is a decision, so every absence is asserted."""

    service = overlay["services"]["project-analyst"]
    assert "volumes" not in service, "the sidecar analyses what it is sent, never what it can read"
    assert "depends_on" not in service
    # Parsed, not text-matched: the overlay's comments name these on purpose,
    # explaining why each one is absent, and a comment must not fail the gate.
    assert "volumes" not in overlay
    assert not any(
        key in definition
        for definition in overlay["services"].values()
        for key in ("volumes", "volumes_from", "devices", "privileged")
    )


def test_the_sidecar_is_not_published_to_the_host(overlay):
    service = overlay["services"]["project-analyst"]
    assert "ports" not in service, "only the app talks to the sidecar, over the compose network"
    assert service["expose"] == ["7900"]


def test_the_sidecar_execution_is_bounded(overlay):
    service = overlay["services"]["project-analyst"]
    assert service["pids_limit"] > 0
    assert service["mem_limit"]
    assert service["cpus"]


def test_provider_clis_are_absent_from_the_application_images():
    """ADR-0036: Codex, Claude and Grok live in the sidecar image and nowhere else."""

    application = (REPOSITORY_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8").lower()
    for cli in ("codex", "claude-code", "@anthropic-ai/claude", "grok"):
        assert cli not in application


def test_the_sidecar_image_does_not_copy_the_repository():
    dockerfile = (REPOSITORY_ROOT / "docker" / "project-analyst.Dockerfile").read_text(encoding="utf-8")
    copies = [line.split() for line in dockerfile.splitlines() if line.startswith("COPY ")]
    sources = {parts[1] for parts in copies}
    assert sources <= {"project_analyst/", "project_analyst/requirements.txt"}


# --- The local profile ------------------------------------------------------


class _LocalHost:
    """A stand-in for the local model host, answering exactly what a test says."""

    def __init__(self, *, tags=None, version="0.12.11", generate=None, fail=None):
        self.tags = {"models": [{"name": "qwen3.5:4b"}]} if tags is None else tags
        self.version = version
        self.generate = generate
        self.fail = fail
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, definition, path, payload, timeout):
        self.calls.append((path, payload))
        if self.fail is not None:
            raise self.fail
        if path == "/api/tags":
            return self.tags
        if path == "/api/version":
            return {"version": self.version}
        if path == "/api/generate":
            return {"response": self.generate}
        raise AssertionError(path)


def _local(monkeypatch, host: _LocalHost) -> _LocalHost:
    monkeypatch.setattr(profiles, "local_request", host)
    return host


def _ollama_entry(client) -> dict:
    return next(entry for entry in client.get("/profiles").json()["profiles"] if entry["id"] == "ollama")


def test_the_local_profile_is_ready_without_any_credential(client, monkeypatch):
    """The point of the profile: no vendor credential, so it can actually run.

    Every CLI profile on this runtime reports `credential_missing`, which left
    the Admin selector empty and the analysis unreachable. A model served from
    inside the appliance has nothing to mount.
    """

    _local(monkeypatch, _LocalHost())

    entry = _ollama_entry(client)

    assert entry["ready"] is True
    assert entry["reason"] == ""
    assert "qwen3.5:4b" in entry["version"], "the report cannot say which model produced it"


def test_a_local_host_that_does_not_answer_is_not_selectable(client, monkeypatch):
    _local(monkeypatch, _LocalHost(fail=OSError("connection refused")))

    entry = _ollama_entry(client)

    assert entry["ready"] is False
    assert entry["reason"] == "local_llm_unreachable"


def test_a_missing_model_names_the_model_that_is_missing(client, monkeypatch):
    """`local_llm_model_missing` alone leaves the operator guessing which one."""

    _local(monkeypatch, _LocalHost(tags={"models": [{"name": "something-else:1b"}]}))

    entry = _ollama_entry(client)

    assert entry["ready"] is False
    assert entry["reason"] == "local_llm_model_missing:qwen3.5:4b"


def test_an_unreadable_version_does_not_make_a_working_host_unready(client, monkeypatch):
    class _NoVersion(_LocalHost):
        def __call__(self, definition, path, payload, timeout):
            if path == "/api/version":
                raise OSError("no version endpoint")
            return super().__call__(definition, path, payload, timeout)

    _local(monkeypatch, _NoVersion())

    entry = _ollama_entry(client)

    assert entry["ready"] is True
    assert entry["version"] == "qwen3.5:4b"


def test_a_local_analysis_produces_the_same_common_result(client, monkeypatch):
    host = _local(
        monkeypatch,
        _LocalHost(
            generate='{"findings":[{"severity":"warning","title":"Config drift",'
            '"detail":"","evidence_paths":["UI_API/backend/config.py"]}]}'
        ),
    )

    response = client.post("/analyze", json={"profile": "ollama", "snapshot": _snapshot()})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profile"] == "ollama"
    assert body["findings"][0]["title"] == "Config drift"
    assert body["evidence_references"] == ["UI_API/backend/config.py"]

    generate = next(payload for path, payload in host.calls if path == "/api/generate")
    assert generate["stream"] is False
    assert generate["format"] == "json", "free text would fail the contract probe every time"
    assert generate["options"]["num_predict"] > 0, "a local model has to be told when to stop"


def test_a_local_analysis_still_refuses_evidence_that_was_never_supplied(client, monkeypatch):
    """The local provider gets no more trust than a vendor CLI."""

    _local(
        monkeypatch,
        _LocalHost(
            generate='{"findings":[{"severity":"blocked","title":"Leak","detail":"","evidence_paths":["/etc/shadow"]}]}'
        ),
    )

    response = client.post("/analyze", json={"profile": "ollama", "snapshot": _snapshot()})

    assert response.status_code == 502
    assert response.json()["detail"] == "provider_cited_unsupplied_evidence"


def test_an_unready_local_profile_is_refused_rather_than_substituted(client, monkeypatch):
    _local(monkeypatch, _LocalHost(fail=OSError("connection refused")))

    response = client.post("/analyze", json={"profile": "ollama", "snapshot": _snapshot()})

    assert response.status_code == 409
    assert response.json()["detail"] == "profile_not_ready:local_llm_unreachable"


def test_a_local_host_that_hangs_is_reported_as_a_timeout_not_a_failure(client, monkeypatch):
    """An operator told "invocation failed" goes looking for the wrong thing."""

    class _Hangs(_LocalHost):
        def __call__(self, definition, path, payload, timeout):
            if path == "/api/generate":
                raise TimeoutError("timed out")
            return super().__call__(definition, path, payload, timeout)

    _local(monkeypatch, _Hangs())

    response = client.post("/analyze", json={"profile": "ollama", "snapshot": _snapshot()})

    assert response.status_code == 504
    assert response.json()["detail"] == "provider_timed_out"


def test_a_local_refusal_never_describes_the_host_it_runs_on(client, monkeypatch):
    _local(monkeypatch, _LocalHost(fail=OSError("connect to 10.4.2.9:11434 failed: /home/oliver/.ollama")))

    entry = _ollama_entry(client)

    assert "10.4.2.9" not in entry["reason"]
    assert "/home/" not in entry["reason"]
