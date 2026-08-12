"""The PostgreSQL job is only evidence if the suite really ran on PostgreSQL.

conftest.py uses `setdefault`, so the backend is whatever the environment asks
for and silently falls back to SQLite otherwise. Without this guard a
misconfigured CI job would keep reporting green while proving nothing about the
database the pilot actually runs on.
"""

import os

import pytest

from modules.voice_turn.postgres_store import PostgresVoiceTurnStore
from modules.voice_turn.sqlite_store import SQLiteVoiceTurnStore
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _requested_backend() -> str:
    return str(os.environ.get("DATABASE_BACKEND", "sqlite") or "sqlite").strip()


def test_configured_backend_matches_the_environment():
    assert postgres_utils.storage_backend() == _requested_backend()


def test_postgres_runs_choose_the_postgres_store():
    """A PostgreSQL run must reach PostgreSQL adapters, not just set a variable."""
    if _requested_backend() != "postgresql":
        return

    assert postgres_utils.use_postgres() is True
    from modules.voice_turn import runtime

    store = runtime.default_module()._store
    assert isinstance(store, PostgresVoiceTurnStore), type(store).__name__


def test_sqlite_runs_choose_the_sqlite_store():
    if _requested_backend() == "postgresql":
        return

    assert postgres_utils.use_postgres() is False
    from modules.voice_turn import runtime

    store = runtime.default_module()._store
    assert isinstance(store, SQLiteVoiceTurnStore)
    assert not isinstance(store, PostgresVoiceTurnStore)
