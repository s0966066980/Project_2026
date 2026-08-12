"""Rules over the backup scripts that a passing drill does not cover.

The drill proves a backup restores. It runs against a live stack, so it cannot
run here. What can run here are the properties that make the drill trustworthy
in the first place: that the backup destination can never be committed, that a
dump without a manifest is refused, and that the scripts do not quietly widen
what they copy.
"""

import re
import stat
from pathlib import Path

import pytest

pytestmark = [pytest.mark.architecture, pytest.mark.security]

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = REPO_ROOT / "scripts" / "backup"
SCRIPTS = ("_common.sh", "backup_postgres.sh", "backup_objects.sh", "verify_backup.sh", "restore_test.sh")


def test_the_four_scripts_the_roadmap_names_exist():
    missing = [name for name in SCRIPTS if not (BACKUP_DIR / name).is_file()]
    assert missing == [], missing


def test_every_script_is_executable_and_fails_on_error():
    """Sourcing `_common.sh` sets errexit in the caller, so either form counts."""

    for name in SCRIPTS:
        path = BACKUP_DIR / name
        assert path.stat().st_mode & stat.S_IXUSR, f"{name} is not executable"
        source = path.read_text(encoding="utf-8")
        declares = "set -euo pipefail" in source
        inherits = "_common.sh" in source and name != "_common.sh"
        assert declares or inherits, f"{name} would continue past a failing command"


def test_the_backup_destination_can_never_be_committed():
    """A backup carries member PII; committing one would publish the database."""

    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".backups/" in ignored

    common = (BACKUP_DIR / "_common.sh").read_text(encoding="utf-8")
    default = re.search(r"^BACKUP_ROOT=(.+)$", common, re.MULTILINE)
    assert default, "BACKUP_ROOT no longer has a discoverable default"
    assert ".backups" in default.group(1), (
        f"the default backup destination is now {default.group(1)}; confirm it is git-ignored"
    )


def test_a_backup_without_a_manifest_is_refused():
    """An unidentified dump cannot be restored with any confidence."""

    for name in ("verify_backup.sh", "restore_test.sh"):
        source = (BACKUP_DIR / name).read_text(encoding="utf-8")
        assert "manifest.json" in source
        assert re.search(r'\[ -f "\$MANIFEST" \] \|\| die', source), f"{name} does not refuse a missing manifest"


def test_the_postgres_backup_records_what_the_dump_is():
    """A dump whose schema version is unknown belongs to no application."""

    source = (BACKUP_DIR / "backup_postgres.sh").read_text(encoding="utf-8")
    for field in ("schema_version", "schema_fingerprint", "table_count", "app_revision", "sha256", "created_at"):
        assert f'"{field}"' in source, f"the manifest does not record {field}"


def test_the_object_backup_excludes_what_is_not_authority():
    """Model weights are re-obtainable; logs and tmp are not business data."""

    source = (BACKUP_DIR / "backup_objects.sh").read_text(encoding="utf-8")
    included = re.search(r"for class in ([a-z ]+); do", source)
    assert included, "the copied data classes are no longer declared in one place"
    assert set(included.group(1).split()) == {"objects", "rag"}, (
        "the object backup changed what it copies; confirm the new set is authority and not working files"
    )


def test_the_restore_drill_never_touches_the_primary_database():
    source = (BACKUP_DIR / "restore_test.sh").read_text(encoding="utf-8")
    assert "RESTORE_DB=" in source
    assert "CREATE DATABASE ${RESTORE_DB}" in source
    assert "DROP DATABASE IF EXISTS ${RESTORE_DB}" in source
    assert "trap cleanup EXIT INT TERM" in source, "a failed drill would leave its database behind"
    assert "pg_restore" in source and '-d "$POSTGRES_DB"' not in source.split("pg_restore", 1)[1][:200], (
        "the drill must restore into the temporary database, never the primary"
    )


def test_verification_does_not_claim_the_backup_is_proven():
    """Checksums pass happily on a dump that will not restore."""

    source = (BACKUP_DIR / "verify_backup.sh").read_text(encoding="utf-8")
    assert "restore is still unproven" in source
