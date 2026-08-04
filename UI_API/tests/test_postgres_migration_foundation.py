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


def test_campaign_touch_migration_is_expand_only_and_scoped() -> None:
    migration = Path(__file__).resolve().parents[1] / "backend/schemas/migrations/0012_campaign_touch_attribution.sql"
    sql = migration.read_text(encoding="utf-8")

    for fragment in (
        "CREATE TABLE campaign_versions",
        "CREATE TABLE recommendation_decisions",
        "CREATE TABLE commercial_touch_events",
        "CREATE TABLE order_touch_attributions",
        "UNIQUE (order_item_id, attribution_type)",
        "FOREIGN KEY (tenant_id, store_id)",
        "idx_commercial_touch_scope_time",
    ):
        assert fragment in sql
    assert "DROP TABLE" not in sql.upper()
    assert "ALTER TABLE promotion_records" not in sql


def test_retired_promotion_cleanup_migration_covers_all_durable_activity_stores() -> None:
    migration = Path(__file__).resolve().parents[1] / "backend/schemas/migrations/0013_retire_legacy_summer_promotions.sql"
    sql = migration.read_text(encoding="utf-8")

    for fragment in (
        "DELETE FROM commercial_touch_events",
        "DELETE FROM analytics_event_log",
        "DELETE FROM recommendation_events",
        "DELETE FROM recommendation_governance_events",
        "DELETE FROM promotion_rule_versions",
        "DELETE FROM promotion_records",
        "DELETE FROM campaign_definitions",
        "summer_drink",
        "summer_food",
    ):
        assert fragment in sql


def test_rag_document_review_states_expand_the_existing_constraint() -> None:
    migration = Path(__file__).resolve().parents[1] / "backend/schemas/migrations/0014_rag_document_review_states.sql"
    sql = migration.read_text(encoding="utf-8")

    assert "rag_document_versions_status_check" in sql
    assert "'approved'" in sql
    assert "'rejected'" in sql
    assert "DROP TABLE" not in sql.upper()


def test_rag_knowledge_lifecycle_adds_background_index_states() -> None:
    migration = Path(__file__).resolve().parents[1] / "backend/schemas/migrations/0015_rag_knowledge_lifecycle.sql"
    sql = migration.read_text(encoding="utf-8")

    assert "rag_document_versions_status_check" in sql
    assert "'indexing'" in sql
    assert "'index_failed'" in sql
    assert "DROP TABLE" not in sql.upper()


def test_rag_intelligence_studio_reset_records_counts_without_content() -> None:
    migration = Path(__file__).resolve().parents[1] / "backend/schemas/migrations/0016_rag_intelligence_studio.sql"
    sql = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS rag_reset_receipts" in sql
    assert "CREATE TABLE IF NOT EXISTS rag_studio_states" in sql
    assert "TRUNCATE TABLE" in sql
    assert "rag_document_versions" in sql
    assert "documents_count" in sql
    assert "versions_count" in sql
    assert "contains_content BOOLEAN NOT NULL DEFAULT FALSE" in sql
    assert "raw_query" not in sql


def test_rag_readiness_confirmation_retains_proof_without_raw_query() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "schemas"
        / "migrations"
        / "0021_rag_readiness_confirmation.sql"
    )
    sql = migration.read_text(encoding="utf-8").lower()

    assert "create table if not exists rag_retrieval_checks" in sql
    assert "index_identity" in sql
    assert "configuration_version" in sql
    assert "result_fingerprint" in sql
    assert "confirmed_by" in sql
    assert "raw_query" not in sql
    assert "full_results" not in sql


def test_checkout_pickup_number_is_store_scoped_and_durable() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "schemas"
        / "migrations"
        / "0022_checkout_pickup_number.sql"
    )
    sql = migration.read_text(encoding="utf-8").lower()

    assert "create table if not exists checkout_pickup_sequences" in sql
    assert "primary key (tenant_id, store_id)" in sql
    assert "add column if not exists pickup_number" in sql


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

    sensitive_value = "credential" + "-sentinel"
    database_url = "postgresql" + f"://member:{sensitive_value}@database.internal:5432/members"
    monkeypatch.setattr(postgres_utils, "database_url", lambda: database_url)
    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(database_url)),
    )

    with pytest.raises(postgres_utils.PostgresUnavailableError) as exc_info:
        postgres_utils.connect()

    assert str(exc_info.value) == "Unable to connect to PostgreSQL"
    assert sensitive_value not in str(exc_info.value)


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
    monkeypatch.setattr(postgres_utils, "migration_connect", lambda: connection)
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

    monkeypatch.delenv("DATABASE_RUNTIME_ROLE", raising=False)
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
    monkeypatch.setattr(postgres_utils, "migration_connect", lambda: connection)
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
    monkeypatch.setattr(manage_postgres_migrations.migrations, "inspect_schema", lambda: invalid_plan)

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
    monkeypatch.setattr(manage_postgres_migrations.migrations, "inspect_schema", lambda: plan)
    monkeypatch.setattr(manage_postgres_migrations.migrations, "require_schema_head", lambda: plan)
    monkeypatch.setattr(manage_postgres_migrations.migrations, "migrate_to_head", lambda: plan)

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
        manage_postgres_migrations.migrations,
        "inspect_schema",
        lambda: (_ for _ in ()).throw(postgres_utils.PostgresUnavailableError("database unavailable")),
    )

    assert manage_postgres_migrations.main(["validate"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "database unavailable" in captured.err
    assert "postgresql://" not in captured.err
