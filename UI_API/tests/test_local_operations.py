"""Executable local pilot operations contracts (no Docker / markdown-only asserts)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

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


def test_native_entrypoint_files_exist() -> None:
    assert (UI_API / "main.py").is_file()
    assert (UI_API / "backend/scripts/run_worker.py").is_file()
    assert (ROOT / "scripts/start_emotion_llama.sh").is_file()
    assert (ROOT / "scripts/start_r1_omni.sh").is_file()
    assert not (ROOT / "deploy/Dockerfile.api").exists()
    assert not (ROOT / "deploy/compose.staging.yml").exists()


def test_local_pilot_env_example_is_postgres_and_secure() -> None:
    text = (ROOT / "config/profiles/local-pilot.env.example").read_text(encoding="utf-8")
    assert "APP_PROFILE=local-pilot" in text
    assert "DATABASE_BACKEND=postgresql" in text
    assert "DATABASE_TOPOLOGY=single" in text
    assert "SECURITY_ENFORCED=true" in text
    assert "ENABLE_DEMO_ROUTES=false" in text
    assert "PAYMENT_BACKEND=manual" in text
    assert "POS_BACKEND=manual" in text
    # No real secrets
    assert "sk-" not in text
    assert "password=" not in text.lower() or "ADMIN_BOOTSTRAP" in text


def test_production_config_fails_fast_on_demo_and_missing_secrets() -> None:
    result = _run_validate_startup(
        {
            "APP_ENV": "production",
            "SECURITY_ENFORCED": "true",
            "ENABLE_DEMO_ROUTES": "true",
            "ENABLE_TEST_ROUTES": "false",
            "ENABLE_DEBUG_ROUTES": "false",
            "ALLOW_UNSAFE_PRODUCTION_ROUTES": "false",
            "DATABASE_BACKEND": "postgresql",
            "DATABASE_TOPOLOGY": "ha",
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
            "ENABLE_LEGACY_KIOSK_TOKEN": "false",
        }
    )
    assert result.returncode != 0
    message = result.stderr + result.stdout
    assert "Runtime Persistence Profile" in message or "Unsafe production configuration" in message


def test_staging_and_pilot_fail_fast_without_postgres() -> None:
    for env_name in ("staging", "pilot"):
        result = _run_validate_startup(
            {
                "APP_ENV": env_name,
                "SECURITY_ENFORCED": "true",
                "ENABLE_DEMO_ROUTES": "false",
                "ENABLE_TEST_ROUTES": "false",
                "ENABLE_DEBUG_ROUTES": "false",
                "ALLOW_UNSAFE_PRODUCTION_ROUTES": "false",
                "DATABASE_BACKEND": "postgresql",
                "DATABASE_TOPOLOGY": "single",
                "DATABASE_URL": "",
                "ADMIN_MEMBER_REF_SECRET": "unique-ref-material-not-placeholder",
                "ALLOW_POSTGRES_JSON_FALLBACK": "false",
                "STRUCTURED_LOGGING_ENABLED": "true",
                "SHARED_RATE_LIMIT_ENABLED": "false",
                "DEFAULT_TENANT_ID": "00000000-0000-4000-8000-000000000001",
                "DEFAULT_STORE_ID": "00000000-0000-4000-8000-000000000002",
                "DEFAULT_DEVICE_ID": "00000000-0000-4000-8000-000000000003",
                "CORS_ORIGINS": "https://kiosk.example",
                "ENABLE_LEGACY_KIOSK_TOKEN": "false",
            }
        )
        assert result.returncode != 0


def test_launch_scripts_are_executable_shell() -> None:
    for rel in (
        "scripts/start_emotion_llama.sh",
        "scripts/start_r1_omni.sh",
    ):
        path = ROOT / rel
        assert path.is_file()
        assert path.stat().st_mode & 0o111
        text = path.read_text(encoding="utf-8")
        assert "set -euo pipefail" in text or "set -e" in text
        # no git checkout of settings
        assert "git checkout -- UI_API/learning_data/settings.json" not in text


def test_local_launchers_start_the_reliable_worker_needed_by_rag_publication() -> None:
    """A local Admin publication must not remain in Indexing forever."""
    for rel in (
        "scripts/start_emotion_llama.sh",
        "scripts/start_r1_omni.sh",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "backend/scripts/run_worker.py" in text
        assert "worker.log" in text


def test_local_launchers_select_and_enable_their_emotion_runtime_profile() -> None:
    expected = {
        "scripts/start_emotion_llama.sh": "emotion_llama",
        "scripts/start_r1_omni.sh": "r1_omni",
    }
    for rel, provider in expected.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert f'export EMOTION_PROVIDER="{provider}"' in text
        assert 'export EMOTION_LLAMA_ENABLED="true"' in text


def test_manual_payment_never_auto_captures() -> None:
    from integrations.payment.manual import ManualPaymentAdapter

    result = ManualPaymentAdapter().capture(provider_reference="manual-x")
    assert result.status == "pending_manual_payment"
