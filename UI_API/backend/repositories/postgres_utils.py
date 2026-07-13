"""PostgreSQL helpers for optional commercial storage backends.

The project defaults to JSON storage. These helpers are imported lazily by
repositories only when `MEMBER_STORAGE_BACKEND=postgres`.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence, TypedDict

import config

SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"
SCHEMA_PATH = SCHEMAS_DIR / "membership_postgres.sql"
MIGRATIONS_DIR = SCHEMAS_DIR / "migrations"
MIGRATION_LOCK_KEY = 781_443_615_300_441_749
MIGRATION_FILE_PATTERN = re.compile(r"^(?P<number>\d{4})_[a-z0-9]+(?:_[a-z0-9]+)*\.sql$")
MigrationState = Literal["applied", "pending", "checksum_mismatch"]


class MigrationRecordPayload(TypedDict):
    version: str
    checksum: str
    applied_checksum: str
    state: MigrationState


class MigrationPlanPayload(TypedDict):
    valid: bool
    applied_count: int
    pending_count: int
    migrations: list[MigrationRecordPayload]
    errors: list[str]


@dataclass(frozen=True)
class MigrationRecord:
    version: str
    checksum: str
    applied_checksum: str
    state: MigrationState

    def as_dict(self) -> MigrationRecordPayload:
        return {
            "version": self.version,
            "checksum": self.checksum,
            "applied_checksum": self.applied_checksum,
            "state": self.state,
        }


@dataclass(frozen=True)
class MigrationPlan:
    migrations: tuple[MigrationRecord, ...]
    unexpected_applied_versions: tuple[str, ...] = ()

    @property
    def applied_versions(self) -> tuple[str, ...]:
        return tuple(record.version for record in self.migrations if record.state == "applied")

    @property
    def pending_versions(self) -> tuple[str, ...]:
        return tuple(record.version for record in self.migrations if record.state == "pending")

    @property
    def errors(self) -> tuple[str, ...]:
        checksum_errors = tuple(
            f"PostgreSQL migration checksum mismatch: {record.version}"
            for record in self.migrations
            if record.state == "checksum_mismatch"
        )
        source_errors = tuple(
            f"PostgreSQL applied migration is missing local migration source: {version}"
            for version in self.unexpected_applied_versions
        )
        return (*checksum_errors, *source_errors)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> MigrationPlanPayload:
        return {
            "valid": self.is_valid,
            "applied_count": len(self.applied_versions),
            "pending_count": len(self.pending_versions),
            "migrations": [record.as_dict() for record in self.migrations],
            "errors": list(self.errors),
        }


class PostgresUnavailableError(RuntimeError):
    pass


class MigrationValidationError(PostgresUnavailableError):
    pass


def storage_backend() -> str:
    return str(config.get("MEMBER_STORAGE_BACKEND", "json") or "json").strip().lower()


def use_postgres() -> bool:
    return storage_backend() == "postgres"


def database_url() -> str:
    return str(config.get("DATABASE_URL", "") or "").strip()


def connect():
    url = database_url()
    if not url:
        raise PostgresUnavailableError("DATABASE_URL is required when MEMBER_STORAGE_BACKEND=postgres")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:
        raise PostgresUnavailableError("psycopg is required for PostgreSQL storage") from exc
    return psycopg.connect(url, row_factory=dict_row)


def migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    return sorted(path for path in MIGRATIONS_DIR.glob("*.sql") if path.is_file())


def migration_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_migration_files(files: Sequence[Path]) -> tuple[Path, ...]:
    ordered_files = tuple(sorted(files, key=lambda path: path.name))
    if not ordered_files:
        raise MigrationValidationError("No PostgreSQL migration files were found")
    for expected_number, path in enumerate(ordered_files, start=1):
        match = MIGRATION_FILE_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationValidationError(f"Invalid PostgreSQL migration filename: {path.name}")
        actual_number = int(match.group("number"))
        if actual_number != expected_number:
            raise MigrationValidationError(
                "PostgreSQL migration versions must be sequential: "
                f"expected {expected_number:04d}, found {actual_number:04d} in {path.name}"
            )
    return ordered_files


def build_migration_plan(files: Sequence[Path], applied: Mapping[str, str]) -> MigrationPlan:
    ordered_files = _validate_migration_files(files)
    local_versions = {path.stem for path in ordered_files}
    migrations: list[MigrationRecord] = []
    for path in ordered_files:
        checksum = migration_checksum(path)
        applied_checksum = str(applied.get(path.stem) or "")
        if not applied_checksum:
            state: MigrationState = "pending"
        elif applied_checksum == checksum:
            state = "applied"
        else:
            state = "checksum_mismatch"
        migrations.append(
            MigrationRecord(
                version=path.stem,
                checksum=checksum,
                applied_checksum=applied_checksum,
                state=state,
            )
        )
    return MigrationPlan(
        migrations=tuple(migrations),
        unexpected_applied_versions=tuple(sorted(set(applied) - local_versions)),
    )


def validate_migration_plan(plan: MigrationPlan, *, require_clean: bool = False) -> None:
    errors = list(plan.errors)
    if require_clean and plan.pending_versions:
        errors.append(f"PostgreSQL migrations are pending: {', '.join(plan.pending_versions)}")
    if errors:
        raise MigrationValidationError("; ".join(errors))


def combined_migration_sql() -> str:
    files = migration_files()
    if not files:
        return SCHEMA_PATH.read_text(encoding="utf-8")
    return "\n\n".join(path.read_text(encoding="utf-8") for path in files)


def _ensure_migration_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _acquire_migration_lock(cur) -> None:
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_KEY,))


def _migration_table_exists(cur) -> bool:
    cur.execute("SELECT to_regclass('schema_migrations') AS value")
    row = cur.fetchone() or {}
    return bool(row.get("value"))


def _fetch_applied_migrations(cur) -> dict[str, str]:
    cur.execute("SELECT version, checksum FROM schema_migrations")
    return {str(row.get("version") or ""): str(row.get("checksum") or "") for row in cur.fetchall()}


def get_migration_plan() -> MigrationPlan:
    files = migration_files()
    _validate_migration_files(files)
    with connect() as conn:
        with conn.cursor() as cur:
            applied = _fetch_applied_migrations(cur) if _migration_table_exists(cur) else {}
    return build_migration_plan(files, applied)


def init_schema() -> None:
    files = migration_files()
    _validate_migration_files(files)
    with connect() as conn:
        with conn.cursor() as cur:
            _acquire_migration_lock(cur)
            _ensure_migration_table(cur)
            applied = _fetch_applied_migrations(cur)
            plan = build_migration_plan(files, applied)
            validate_migration_plan(plan)
            paths_by_version = {path.stem: path for path in files}
            for record in plan.migrations:
                if record.state == "applied":
                    continue
                path = paths_by_version[record.version]
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, checksum)
                    VALUES (%s, %s)
                    """,
                    (record.version, record.checksum),
                )
        conn.commit()


def apply_migrations() -> MigrationPlan:
    init_schema()
    plan = get_migration_plan()
    validate_migration_plan(plan, require_clean=True)
    return plan
