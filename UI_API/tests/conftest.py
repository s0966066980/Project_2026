"""Shared pytest fixtures — temporary data dirs only; never rewrite tracked learning_data."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _json_storage_when_no_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep unit tests offline unless DATABASE_URL is explicitly provided."""

    if os.environ.get("DATABASE_URL", "").strip():
        return
    monkeypatch.setenv("MEMBER_STORAGE_BACKEND", "json")
    monkeypatch.setenv("DATABASE_URL", "")
    if os.environ.get("APP_ENV", "").strip() in {"", "test"}:
        monkeypatch.setenv("APP_ENV", "test")
    # Isolate mutable test settings from tracked learning_data
    data_dir = tmp_path / "test_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_path = data_dir / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("TEST_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TEST_SETTINGS_PATH", str(settings_path))
    try:
        import config

        monkeypatch.setattr(config, "LEARNING_DATA_DIR", str(data_dir), raising=False)
        if hasattr(config, "SETTINGS_JSON_PATH"):
            monkeypatch.setattr(config, "SETTINGS_JSON_PATH", str(settings_path), raising=False)
    except Exception:
        pass
    try:
        from repositories import postgres_utils

        monkeypatch.setattr(postgres_utils, "use_postgres", lambda: False)
        monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "json")
    except Exception:
        pass
