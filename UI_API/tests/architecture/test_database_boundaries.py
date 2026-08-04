"""Architecture: local-pilot data path validation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "UI_API/backend/scripts/validate_local_pilot_data_paths.py"


def test_validate_local_pilot_data_paths_script_runs() -> None:
    env = os.environ.copy()
    env.pop("APP_PROFILE", None)
    env["DATABASE_BACKEND"] = "sqlite"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT / "UI_API"),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_pilot_profile_requires_postgres(monkeypatch) -> None:
    env = os.environ.copy()
    for key in list(env):
        if key in {
            "DATABASE_URL",
            "DATABASE_URL_FILE",
            "REDIS_URL",
            "DATABASE_BACKEND",
            "SECURITY_ENFORCED",
            "ENABLE_DEMO_ROUTES",
            "APP_ENV",
            "APP_PROFILE",
        }:
            env.pop(key, None)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "UI_API/backend/scripts/validate_local_environment.py"),
            "--profile",
            "local-pilot",
        ],
        cwd=str(ROOT / "UI_API"),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "FAIL:" in result.stdout
