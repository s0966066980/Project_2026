"""Milestone L3 local profile validation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "UI_API/backend/scripts/validate_local_environment.py"


def _run(profile: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    # Clear commercial keys so profile defaults apply cleanly
    for key in (
        "DATABASE_URL",
        "DATABASE_URL_FILE",
        "REDIS_URL",
        "MEMBER_STORAGE_BACKEND",
        "SECURITY_ENFORCED",
        "ENABLE_DEMO_ROUTES",
        "ENABLE_DEBUG_ROUTES",
        "APP_ENV",
        "ADMIN_LOCAL_MANAGER_AUTH_ENABLED",
        "ENABLE_LEGACY_KIOSK_TOKEN",
        "KIOSK_DEVICE_TOKEN",
        "ADMIN_MEMBER_REF_SECRET",
        "OBJECT_STORAGE_SIGNING_SECRET",
        "DEFAULT_TENANT_ID",
        "DEFAULT_STORE_ID",
        "DEFAULT_DEVICE_ID",
        "ENABLE_NGROK",
    ):
        merged.pop(key, None)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--profile", profile, "--no-env-files"],
        cwd=str(ROOT / "UI_API"),
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def test_local_dev_profile_requires_local_postgresql() -> None:
    result = _run("local-dev")
    assert result.returncode != 0
    assert "DATABASE_URL" in result.stdout
    assert "postgresql://" not in result.stdout.lower()


def test_local_full_fails_without_required_settings() -> None:
    result = _run("local-full")
    assert result.returncode != 0
    assert "FAIL:" in result.stdout
    assert "DATABASE_URL" in result.stdout or "REDIS_URL" in result.stdout


def test_local_postgres_requires_database_url() -> None:
    missing = _run("local-postgres")
    assert missing.returncode != 0
    ok = _run(
        "local-postgres",
        {"DATABASE_BACKEND": "postgresql", "DATABASE_URL": "postgresql://local/test"},
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_local_pilot_identity_cannot_be_downgraded_by_ambient_environment() -> None:
    result = _run(
        "local-pilot",
        {
            "APP_ENV": "development",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_TOPOLOGY": "ha",
            "SECURITY_ENFORCED": "false",
            "ENABLE_DEMO_ROUTES": "true",
            "ENABLE_DEBUG_ROUTES": "true",
            "DATABASE_URL": "postgresql://local/test",
        },
    )

    assert "INFO: APP_ENV=pilot" in result.stdout
    assert "INFO: DATABASE_BACKEND=postgresql" in result.stdout
    assert "INFO: DATABASE_TOPOLOGY=single" in result.stdout
    assert "INFO: SECURITY_ENFORCED=true" in result.stdout


def test_local_pilot_runs_the_real_startup_safety_contract() -> None:
    result = _run(
        "local-pilot",
        {"DATABASE_URL": "postgresql://local/test"},
    )

    assert result.returncode != 0
    assert "startup safety contract" in result.stdout
    assert "ADMIN_MEMBER_REF_SECRET" in result.stdout


def test_profile_list_includes_all_local_profiles() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--list"],
        cwd=str(ROOT / "UI_API"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    for name in ("local-dev", "local-postgres", "local-full", "local-pilot", "test", "ci"):
        assert name in result.stdout
