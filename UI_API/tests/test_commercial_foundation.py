"""Milestone 0 repository governance regression tests."""

from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_commercial_foundation_documents_exist() -> None:
    required_paths = [
        "AGENTS.md",
        ".env.example",
        ".github/workflows/ci.yml",
        "docs/architecture/CURRENT_STATE.md",
        "docs/architecture/TARGET_ARCHITECTURE.md",
        "docs/architecture/ADR-0001-modular-monolith-first.md",
        "docs/architecture/ADR-0002-frontend-deployment-boundary.md",
        "docs/architecture/ADR-0003-ai-provider-adapter.md",
        "docs/architecture/ADR-0004-member-identity-migration.md",
        "docs/commercialization/ROADMAP.md",
        "docs/commercialization/RISK_REGISTER.md",
        "docs/commercialization/MEMBER_MIGRATION_PLAN.md",
        "UI_API/frontend/package-lock.json",
    ]

    missing = [path for path in required_paths if not (REPOSITORY_ROOT / path).is_file()]
    assert missing == []


def test_agents_is_not_ignored_and_local_artifacts_are_ignored() -> None:
    rules = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    active_rules = {line.strip() for line in rules if line.strip() and not line.lstrip().startswith("#")}

    assert "AGENTS.md" not in active_rules
    assert ".codegraph/" in active_rules
    assert "tmp_visual_checks/" in active_rules
    assert "Emotion-LLaMA/checkpoints/" in active_rules
    assert "R1-Omni/models/" in active_rules


def test_environment_example_contains_no_filled_credentials() -> None:
    values = {}
    for line in (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value

    sensitive_keys = {
        "ADMIN_API_TOKEN",
        "KIOSK_DEVICE_TOKEN",
        "ADMIN_MEMBER_REF_SECRET",
        "POS_DEMO_TOKEN",
        "ADMIN_DEMO_TOKEN",
        "WS_DEMO_TOKEN",
        "JWT_SECRET",
        "OBJECT_STORAGE_ACCESS_KEY",
        "OBJECT_STORAGE_SECRET_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "STT_API_KEY",
        "TTS_API_KEY",
        "NGROK_AUTHTOKEN",
    }
    assert sensitive_keys.issubset(values)
    assert all(values[key] in {"", "CHANGE_ME"} for key in sensitive_keys)


def test_frontend_lockfile_matches_declared_typescript_dependency() -> None:
    package = json.loads(
        (REPOSITORY_ROOT / "UI_API/frontend/package.json").read_text(encoding="utf-8")
    )
    lockfile = json.loads(
        (REPOSITORY_ROOT / "UI_API/frontend/package-lock.json").read_text(encoding="utf-8")
    )

    assert lockfile["lockfileVersion"] == 3
    assert (
        lockfile["packages"][""]["devDependencies"]["typescript"]
        == package["devDependencies"]["typescript"]
    )


def test_ci_avoids_model_and_gpu_startup() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "pytest -q tests" in workflow
    assert "npm ci --ignore-scripts" in workflow
    assert "npm run typecheck" in workflow
    assert "npm run syntax" in workflow
    assert "ollama pull" not in workflow
    assert "app_EmotionLlamaClient.py" not in workflow
    assert "r1_omni_server.py" not in workflow
