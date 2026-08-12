"""Status vocabularies are hand-written twice, so they must be compared automatically.

Every table a module stores in SQLite declares its allowed statuses inline, while
PostgreSQL gets the same list through a migration. SQLite has no migration runner
and creates its tables with CREATE TABLE IF NOT EXISTS, so a value added to one
side never fails loudly on the other: the test suite runs on a fresh SQLite file
and stays green while the pilot's PostgreSQL rejects the write.

Adding a status means editing both sources. This test is what notices when only
one of them was edited.
"""

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract]
BACKEND = Path(__file__).resolve().parents[1] / "backend"
MIGRATIONS = BACKEND / "schemas" / "migrations"

_TABLE = re.compile(r"CREATE TABLE(?: IF NOT EXISTS)?\s+(\w+)\s*\((.*?)\n\)\s*;", re.S | re.I)
_STATUS_CHECK = re.compile(r"status\s+TEXT\s+NOT NULL\s+CHECK\s*\(\s*status\s+IN\s*\((.*?)\)\s*\)", re.S | re.I)
_ADD_CONSTRAINT = re.compile(r"ALTER TABLE\s+(\w+)\s+ADD CONSTRAINT \w+ CHECK \(status IN \((.*?)\)\)", re.S | re.I)


def _values(sql: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", sql))


def _statuses_in_table_body(body: str) -> set[str] | None:
    match = _STATUS_CHECK.search(body)
    return _values(match.group(1)) if match else None


def _sqlite_status_tables() -> dict[str, tuple[str, set[str]]]:
    found: dict[str, tuple[str, set[str]]] = {}
    for path in sorted((BACKEND / "modules").glob("*/sqlite_store.py")):
        for table, body in _TABLE.findall(path.read_text(encoding="utf-8")):
            statuses = _statuses_in_table_body(body)
            if statuses:
                found[table] = (str(path.relative_to(BACKEND)), statuses)
    return found


def _migration_status_tables() -> dict[str, tuple[str, set[str]]]:
    """Replay the migrations in order so a later ALTER wins, as it does in PostgreSQL."""
    found: dict[str, tuple[str, set[str]]] = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        for table, body in _TABLE.findall(sql):
            statuses = _statuses_in_table_body(body)
            if statuses:
                found[table] = (path.name, statuses)
        for table, values in _ADD_CONSTRAINT.findall(sql):
            found[table] = (path.name, _values(values))
    return found


def test_status_vocabularies_agree_across_both_schema_sources():
    sqlite_tables = _sqlite_status_tables()
    migration_tables = _migration_status_tables()
    shared = sorted(set(sqlite_tables) & set(migration_tables))
    assert shared, "no table declares its statuses in both schema sources any more"

    drift = {}
    for table in shared:
        sqlite_path, sqlite_statuses = sqlite_tables[table]
        migration_file, migration_statuses = migration_tables[table]
        if sqlite_statuses != migration_statuses:
            drift[table] = {
                "sqlite_only": sorted(sqlite_statuses - migration_statuses),
                "migration_only": sorted(migration_statuses - sqlite_statuses),
                "sources": (sqlite_path, migration_file),
            }

    assert drift == {}, f"status vocabularies drifted between SQLite and the migrations: {drift}"


def test_voice_turn_statuses_match_the_module_state_machine():
    """The module decides which statuses are terminal; storage must be able to hold them."""
    from modules.voice_turn.module import TERMINAL

    _, stored = _sqlite_status_tables()["voice_turns"]

    assert TERMINAL <= stored, f"terminal statuses the store cannot hold: {sorted(TERMINAL - stored)}"


def test_voice_turn_statuses_match_the_kiosk_protocol():
    """The kiosk refuses unknown event types, so a new terminal status must be listed there too."""
    from modules.voice_turn.module import TERMINAL

    protocol = (BACKEND.parent / "frontend" / "kiosk" / "voiceTurnProtocol.js").read_text(encoding="utf-8")
    known = _values(protocol.split("KNOWN_EVENT_TYPES", 1)[1].split("]", 1)[0])

    missing = {status for status in TERMINAL if status not in known}
    assert not missing, f"terminal statuses the kiosk would reject as unknown events: {sorted(missing)}"
