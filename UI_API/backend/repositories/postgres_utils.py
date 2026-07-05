"""PostgreSQL helpers for optional commercial storage backends.

The project defaults to JSON storage. These helpers are imported lazily by
repositories only when `MEMBER_STORAGE_BACKEND=postgres`.
"""
from pathlib import Path
import hashlib

import config


SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"
SCHEMA_PATH = SCHEMAS_DIR / "membership_postgres.sql"
MIGRATIONS_DIR = SCHEMAS_DIR / "migrations"


class PostgresUnavailableError(RuntimeError):
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


def _fetch_applied_migrations(cur) -> dict[str, str]:
    cur.execute("SELECT version, checksum FROM schema_migrations")
    return {
        str(row.get("version") or ""): str(row.get("checksum") or "")
        for row in cur.fetchall()
    }


def init_schema() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            files = migration_files()
            if not files:
                cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                conn.commit()
                return

            _ensure_migration_table(cur)
            applied = _fetch_applied_migrations(cur)
            for path in files:
                version = path.stem
                checksum = migration_checksum(path)
                if version in applied:
                    if applied[version] != checksum:
                        raise PostgresUnavailableError(
                            f"PostgreSQL migration checksum mismatch: {version}"
                        )
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, checksum)
                    VALUES (%s, %s)
                    """,
                    (version, checksum),
                )
        conn.commit()
