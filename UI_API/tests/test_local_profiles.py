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
        "REDIS_URL",
        "MEMBER_STORAGE_BACKEND",
        "SECURITY_ENFORCED",
        "ENABLE_DEMO_ROUTES",
        "ENABLE_DEBUG_ROUTES",
        "APP_ENV",
    ):
        merged.pop(key, None)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--profile", profile],
        cwd=str(ROOT / "UI_API"),
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def test_local_dev_profile_passes_without_database() -> None:
    result = _run("local-dev")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout
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
        {"MEMBER_STORAGE_BACKEND": "postgres", "DATABASE_URL": "postgresql://local/test"},
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr


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
