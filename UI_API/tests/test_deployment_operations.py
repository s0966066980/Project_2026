"""Milestone 2F deployment contract, env fail-fast, and operations gates."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI_API = ROOT / "UI_API"


def _run_validate_startup(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    merged["PYTHONDONTWRITEBYTECODE"] = "1"
    code = "import config; config.validate_startup_config()"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(UI_API),
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def test_deployment_docs_define_process_and_image_boundaries() -> None:
    deployment = (ROOT / "docs/operations/DEPLOYMENT.md").read_text(encoding="utf-8")
    for fragment in (
        "API",
        "Worker",
        "PostgreSQL",
        "Redis",
        "Emotion-LLaMA",
        "R1-Omni",
        "GPU",
        "pre-deploy",
        "post-deploy",
        "rollback",
        "forward-only",
        "staging",
        "pilot",
        "production",
        "development",
        "NOT Production Certified",
    ):
        assert fragment in deployment


def test_api_image_excludes_gpu_model_trees() -> None:
    api_dockerfile = (ROOT / "deploy/Dockerfile.api").read_text(encoding="utf-8")
    worker_dockerfile = (ROOT / "deploy/Dockerfile.worker").read_text(encoding="utf-8")
    assert "COPY Emotion-LLaMA" not in api_dockerfile
    assert "COPY R1-Omni" not in api_dockerfile
    assert "COPY Emotion-LLaMA" not in worker_dockerfile
    assert "COPY R1-Omni" not in worker_dockerfile
    assert "COPY UI_API" in api_dockerfile
    assert "run_worker.py" in worker_dockerfile


def test_env_examples_separate_non_production_from_production() -> None:
    staging = (ROOT / "deploy/env-templates/staging.example").read_text(encoding="utf-8")
    pilot = (ROOT / "deploy/env-templates/pilot.example").read_text(encoding="utf-8")
    production = (ROOT / "deploy/env-templates/production.example").read_text(encoding="utf-8")
    for text in (staging, pilot, production):
        assert "ENABLE_DEMO_ROUTES=false" in text
        assert "MEMBER_STORAGE_BACKEND=postgres" in text
        assert "ALLOW_POSTGRES_JSON_FALLBACK=false" in text
        assert "CHANGE_ME" in text or "inject" in text.lower() or "Secret" in text
    assert "APP_ENV=staging" in staging
    assert "APP_ENV=pilot" in pilot
    assert "APP_ENV=production" in production
    assert "SECURITY_ENFORCED=true" in production


def test_production_config_fails_fast_on_demo_and_missing_secrets() -> None:
    result = _run_validate_startup(
        {
            "APP_ENV": "production",
            "SECURITY_ENFORCED": "true",
            "ENABLE_DEMO_ROUTES": "true",
            "ENABLE_TEST_ROUTES": "false",
            "ENABLE_DEBUG_ROUTES": "false",
            "ALLOW_UNSAFE_PRODUCTION_ROUTES": "false",
            "MEMBER_STORAGE_BACKEND": "json",
            "DATABASE_URL": "",
            "ADMIN_MEMBER_REF_SECRET": "",
            "ALLOW_POSTGRES_JSON_FALLBACK": "false",
            "STRUCTURED_LOGGING_ENABLED": "true",
            "SHARED_RATE_LIMIT_ENABLED": "true",
            "REDIS_URL": "",
            "DEFAULT_TENANT_ID": "00000000-0000-4000-8000-000000000001",
            "DEFAULT_STORE_ID": "00000000-0000-4000-8000-000000000002",
            "DEFAULT_DEVICE_ID": "00000000-0000-4000-8000-000000000003",
            "CORS_ORIGINS": "https://kiosk.example",
            "ENABLE_LEGACY_ADMIN_TOKEN": "false",
            "ENABLE_LEGACY_KIOSK_TOKEN": "false",
        }
    )
    assert result.returncode != 0
    message = result.stderr + result.stdout
    assert "Unsafe production configuration" in message
    assert "ENABLE_DEMO_ROUTES" in message or "MEMBER_STORAGE_BACKEND" in message


def test_staging_and_pilot_also_fail_fast_without_postgres() -> None:
    for env_name in ("staging", "pilot"):
        result = _run_validate_startup(
            {
                "APP_ENV": env_name,
                "SECURITY_ENFORCED": "true",
                "ENABLE_DEMO_ROUTES": "false",
                "ENABLE_TEST_ROUTES": "false",
                "ENABLE_DEBUG_ROUTES": "false",
                "ALLOW_UNSAFE_PRODUCTION_ROUTES": "false",
                "MEMBER_STORAGE_BACKEND": "json",
                "DATABASE_URL": "",
                "ADMIN_MEMBER_REF_SECRET": "unique-ref-material-not-placeholder",
                "ALLOW_POSTGRES_JSON_FALLBACK": "false",
                "STRUCTURED_LOGGING_ENABLED": "true",
                "SHARED_RATE_LIMIT_ENABLED": "false",
                "DEFAULT_TENANT_ID": "00000000-0000-4000-8000-000000000001",
                "DEFAULT_STORE_ID": "00000000-0000-4000-8000-000000000002",
                "DEFAULT_DEVICE_ID": "00000000-0000-4000-8000-000000000003",
                "CORS_ORIGINS": "https://kiosk.example",
                "ENABLE_LEGACY_ADMIN_TOKEN": "false",
                "ENABLE_LEGACY_KIOSK_TOKEN": "false",
            }
        )
        assert result.returncode != 0
        message = result.stderr + result.stdout
        assert "MEMBER_STORAGE_BACKEND" in message or "DATABASE_URL" in message


def test_pre_and_post_deploy_scripts_cover_release_gates() -> None:
    pre = (ROOT / "scripts/pre_deploy_check.sh").read_text(encoding="utf-8")
    post = (ROOT / "scripts/post_deploy_smoke.sh").read_text(encoding="utf-8")
    for fragment in ("validate --require-clean", "validate_commercial_scope", "backup", "set -euo pipefail"):
        assert fragment in pre
    for fragment in ("/live", "/ready", "set -euo pipefail"):
        assert fragment in post


def test_restore_drill_template_records_required_fields() -> None:
    template = (ROOT / "docs/operations/RESTORE_DRILL_TEMPLATE.md").read_text(encoding="utf-8")
    for fragment in (
        "date",
        "source version",
        "target",
        "duration",
        "row counts",
        "migration",
        "smoke",
        "isolated",
    ):
        assert fragment.lower() in template.lower()
    script = (ROOT / "scripts/record_restore_drill.sh").read_text(encoding="utf-8")
    assert "RESTORE_DRILL" in script or "restore-drills" in script
    assert "set -euo pipefail" in script


def test_compose_staging_separates_api_worker_postgres_redis() -> None:
    compose = (ROOT / "deploy/compose.staging.yml").read_text(encoding="utf-8")
    for service in ("api:", "worker:", "postgres:", "redis:"):
        assert service in compose
    assert "image: emotion" not in compose.lower()
    assert "build:" in compose
    assert "Dockerfile.api" in compose
    assert "Dockerfile.worker" in compose
