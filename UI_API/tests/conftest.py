"""Shared pytest fixtures for local JSON-first runs.

When DATABASE_URL is unset, force JSON storage so unit tests do not attempt
PostgreSQL connections via polluted learning_data/settings.json.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / "UI_API" / "learning_data" / "settings.json"


@pytest.fixture(autouse=True)
def _json_storage_when_no_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.environ.get("DATABASE_URL", "").strip():
        return
    monkeypatch.setenv("MEMBER_STORAGE_BACKEND", "json")
    monkeypatch.setenv("DATABASE_URL", "")
    if os.environ.get("APP_ENV", "").strip() in {"", "test"}:
        monkeypatch.setenv("APP_ENV", "test")
    try:
        from repositories import postgres_utils

        monkeypatch.setattr(postgres_utils, "use_postgres", lambda: False)
        monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "json")
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def _restore_settings_file_after_session() -> None:
    yield
    # Best-effort cleanup so local dev is not left in production fail-closed mode.
    try:
        import subprocess

        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "checkout", "--", "UI_API/learning_data/settings.json"],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass
