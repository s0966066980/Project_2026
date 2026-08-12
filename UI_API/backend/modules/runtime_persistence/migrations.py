"""Explicit PostgreSQL schema maintenance interface.

Runtime repositories never import this module. Maintenance commands may move
the schema forward; startup and bootstrap may only require an already-clean
schema.
"""

from __future__ import annotations

from repositories import postgres_utils

MigrationPlan = postgres_utils.MigrationPlan
MigrationValidationError = postgres_utils.MigrationValidationError


def local_schema_head() -> str:
    """The newest migration this build carries, read from disk rather than the database.

    A build reports the schema it was built against even when the database is
    unreachable, which is exactly when an operator is trying to find out which
    version is deployed.
    """

    files = postgres_utils.migration_files()
    return files[-1].stem if files else ""


def inspect_schema() -> MigrationPlan:
    """Read migration state without changing schema."""

    return postgres_utils.get_migration_plan()


def require_schema_head() -> MigrationPlan:
    """Fail unless the database exactly matches the local migration head."""

    plan = inspect_schema()
    postgres_utils.validate_migration_plan(plan, require_clean=True)
    return plan


def migrate_to_head() -> MigrationPlan:
    """Apply forward migrations using the migration role, then verify runtime access."""

    return postgres_utils.apply_migrations()


__all__ = [
    "MigrationPlan",
    "MigrationValidationError",
    "inspect_schema",
    "local_schema_head",
    "migrate_to_head",
    "require_schema_head",
]
