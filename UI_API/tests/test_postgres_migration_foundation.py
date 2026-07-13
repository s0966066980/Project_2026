"""Unit tests for the PostgreSQL migration foundation."""

from __future__ import annotations

from pathlib import Path

import pytest


def _write_migration(directory: Path, name: str, sql: str = "SELECT 1;\n") -> Path:
    path = directory / name
    path.write_text(sql, encoding="utf-8")
    return path


def test_migration_plan_reports_applied_and_pending_files(tmp_path: Path) -> None:
    from repositories import postgres_utils

    first = _write_migration(tmp_path, "0001_initial.sql")
    second = _write_migration(tmp_path, "0002_add_index.sql")

    plan = postgres_utils.build_migration_plan(
        [first, second],
        {first.stem: postgres_utils.migration_checksum(first)},
    )

    assert plan.is_valid is True
    assert plan.applied_versions == (first.stem,)
    assert plan.pending_versions == (second.stem,)


def test_migration_plan_rejects_checksum_mismatch(tmp_path: Path) -> None:
    from repositories import postgres_utils

    migration = _write_migration(tmp_path, "0001_initial.sql")
    plan = postgres_utils.build_migration_plan([migration], {migration.stem: "wrong-checksum"})

    assert plan.is_valid is False
    assert any("checksum mismatch" in error for error in plan.errors)
    with pytest.raises(postgres_utils.MigrationValidationError, match="checksum mismatch"):
        postgres_utils.validate_migration_plan(plan)


def test_migration_manifest_requires_canonical_sequential_versions(tmp_path: Path) -> None:
    from repositories import postgres_utils

    first = _write_migration(tmp_path, "0001_initial.sql")
    third = _write_migration(tmp_path, "0003_gap.sql")

    with pytest.raises(postgres_utils.MigrationValidationError, match="sequential"):
        postgres_utils.build_migration_plan([first, third], {})


def test_migration_manifest_rejects_missing_migration_sources() -> None:
    from repositories import postgres_utils

    with pytest.raises(postgres_utils.MigrationValidationError, match="No PostgreSQL migration files"):
        postgres_utils.build_migration_plan([], {})


def test_migration_manifest_rejects_noncanonical_filename(tmp_path: Path) -> None:
    from repositories import postgres_utils

    migration = _write_migration(tmp_path, "1-Initial.sql")

    with pytest.raises(postgres_utils.MigrationValidationError, match="Invalid PostgreSQL migration filename"):
        postgres_utils.build_migration_plan([migration], {})


def test_validate_migration_plan_can_require_clean_state(tmp_path: Path) -> None:
    from repositories import postgres_utils

    migration = _write_migration(tmp_path, "0001_initial.sql")
    plan = postgres_utils.build_migration_plan([migration], {})

    with pytest.raises(postgres_utils.MigrationValidationError, match="migrations are pending"):
        postgres_utils.validate_migration_plan(plan, require_clean=True)


def test_migration_plan_rejects_applied_version_missing_from_source(tmp_path: Path) -> None:
    from repositories import postgres_utils

    migration = _write_migration(tmp_path, "0001_initial.sql")
    plan = postgres_utils.build_migration_plan(
        [migration],
        {
            migration.stem: postgres_utils.migration_checksum(migration),
            "0002_missing_source": "stored-checksum",
        },
    )

    assert plan.is_valid is False
    assert any("missing local migration" in error for error in plan.errors)


def test_migration_lock_uses_parameterized_transaction_advisory_lock() -> None:
    from repositories import postgres_utils

    class RecordingCursor:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
            self.calls.append((sql, params))

    cursor = RecordingCursor()

    postgres_utils._acquire_migration_lock(cursor)

    assert cursor.calls == [
        ("SELECT pg_advisory_xact_lock(%s)", (postgres_utils.MIGRATION_LOCK_KEY,)),
    ]


def test_connect_wraps_driver_error_without_exposing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    from repositories import postgres_utils

    database_url = "postgresql://member:super-secret@database.internal:5432/members"
    monkeypatch.setattr(postgres_utils, "database_url", lambda: database_url)
    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(database_url)),
    )

    with pytest.raises(postgres_utils.PostgresUnavailableError) as exc_info:
        postgres_utils.connect()

    assert str(exc_info.value) == "Unable to connect to PostgreSQL"
    assert "super-secret" not in str(exc_info.value)


def test_init_schema_locks_before_validation_and_skips_applied_migration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from repositories import postgres_utils

    migration = _write_migration(tmp_path, "0001_initial.sql", "CREATE TABLE should_not_run (id INT);\n")
    checksum = postgres_utils.migration_checksum(migration)
    events: list[str] = []

    class FakeCursor:
        def __init__(self) -> None:
            self.executed_sql: list[str] = []

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, _params: tuple[object, ...] = ()) -> None:
            self.executed_sql.append(sql)

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.commits = 0

        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def commit(self) -> None:
            self.commits += 1

    connection = FakeConnection()
    monkeypatch.setattr(postgres_utils, "connect", lambda: connection)
    monkeypatch.setattr(postgres_utils, "migration_files", lambda: [migration])
    monkeypatch.setattr(postgres_utils, "_acquire_migration_lock", lambda _cursor: events.append("lock"))
    monkeypatch.setattr(postgres_utils, "_ensure_migration_table", lambda _cursor: events.append("ensure"))
    monkeypatch.setattr(
        postgres_utils,
        "_fetch_applied_migrations",
        lambda _cursor: events.append("fetch") or {migration.stem: checksum},
    )

    postgres_utils.init_schema()
    postgres_utils.init_schema()

    assert events == ["lock", "ensure", "fetch", "lock", "ensure", "fetch"]
    assert connection.commits == 2
    assert migration.read_text(encoding="utf-8") not in connection.cursor_instance.executed_sql


def test_get_migration_plan_reports_pending_when_tracking_table_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from repositories import postgres_utils

    migration = _write_migration(tmp_path, "0001_initial.sql")

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _sql: str, _params: tuple[object, ...] = ()) -> None:
            return None

        def fetchone(self) -> dict[str, object]:
            return {"value": None}

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    monkeypatch.setattr(postgres_utils, "migration_files", lambda: [migration])
    monkeypatch.setattr(postgres_utils, "connect", lambda: FakeConnection())

    plan = postgres_utils.get_migration_plan()

    assert plan.pending_versions == (migration.stem,)


def test_init_schema_applies_pending_migration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from repositories import postgres_utils

    migration = _write_migration(tmp_path, "0001_initial.sql", "CREATE TABLE example (id INT);\n")

    class FakeCursor:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
            self.calls.append((sql, params))

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.commits = 0

        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def commit(self) -> None:
            self.commits += 1

    connection = FakeConnection()
    monkeypatch.setattr(postgres_utils, "migration_files", lambda: [migration])
    monkeypatch.setattr(postgres_utils, "connect", lambda: connection)
    monkeypatch.setattr(postgres_utils, "_acquire_migration_lock", lambda _cursor: None)
    monkeypatch.setattr(postgres_utils, "_ensure_migration_table", lambda _cursor: None)
    monkeypatch.setattr(postgres_utils, "_fetch_applied_migrations", lambda _cursor: {})

    postgres_utils.init_schema()

    checksum = postgres_utils.migration_checksum(migration)
    assert connection.cursor_instance.calls == [
        (migration.read_text(encoding="utf-8"), ()),
        (
            """
                    INSERT INTO schema_migrations (version, checksum)
                    VALUES (%s, %s)
                    """,
            (migration.stem, checksum),
        ),
    ]
    assert connection.commits == 1


def test_apply_migrations_returns_validated_clean_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    from repositories import postgres_utils

    plan = postgres_utils.MigrationPlan(
        migrations=(
            postgres_utils.MigrationRecord(
                version="0001_initial",
                checksum="checksum",
                applied_checksum="checksum",
                state="applied",
            ),
        )
    )
    events: list[str] = []
    monkeypatch.setattr(postgres_utils, "init_schema", lambda: events.append("apply"))
    monkeypatch.setattr(postgres_utils, "get_migration_plan", lambda: plan)

    result = postgres_utils.apply_migrations()

    assert events == ["apply"]
    assert result is plan


def test_status_outputs_invalid_plan_before_returning_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from backend.scripts import manage_postgres_migrations
    from repositories import postgres_utils

    invalid_plan = postgres_utils.MigrationPlan(
        migrations=(),
        unexpected_applied_versions=("0001_missing_source",),
    )
    monkeypatch.setattr(postgres_utils, "get_migration_plan", lambda: invalid_plan)

    exit_code = manage_postgres_migrations.main(["status"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert '"valid": false' in captured.out
    assert "missing local migration source" in captured.out


def test_cli_validate_and_apply_output_valid_plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from backend.scripts import manage_postgres_migrations
    from repositories import postgres_utils

    plan = postgres_utils.MigrationPlan(
        migrations=(
            postgres_utils.MigrationRecord(
                version="0001_initial",
                checksum="checksum",
                applied_checksum="checksum",
                state="applied",
            ),
        )
    )
    monkeypatch.setattr(postgres_utils, "get_migration_plan", lambda: plan)
    monkeypatch.setattr(postgres_utils, "apply_migrations", lambda: plan)

    assert manage_postgres_migrations.main(["validate", "--require-clean"]) == 0
    assert '"valid": true' in capsys.readouterr().out
    assert manage_postgres_migrations.main(["apply"]) == 0
    assert '"pending_count": 0' in capsys.readouterr().out


def test_cli_returns_failure_without_leaking_database_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from backend.scripts import manage_postgres_migrations
    from repositories import postgres_utils

    monkeypatch.setattr(
        postgres_utils,
        "get_migration_plan",
        lambda: (_ for _ in ()).throw(postgres_utils.PostgresUnavailableError("database unavailable")),
    )

    assert manage_postgres_migrations.main(["validate"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "database unavailable" in captured.err
    assert "postgresql://" not in captured.err
