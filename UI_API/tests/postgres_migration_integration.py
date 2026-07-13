"""CI-only PostgreSQL migration integration tests.

This file is intentionally not named ``test_*.py`` so the JSON-only default
suite does not require a local PostgreSQL server. GitHub Actions invokes it
explicitly against a disposable PostgreSQL service.
"""

from __future__ import annotations


def test_postgres_migrations_apply_idempotently() -> None:
    from repositories import postgres_utils

    initial = postgres_utils.get_migration_plan()
    assert initial.is_valid is True
    assert initial.pending_versions

    postgres_utils.init_schema()
    first_apply = postgres_utils.get_migration_plan()
    postgres_utils.init_schema()
    second_apply = postgres_utils.get_migration_plan()

    assert first_apply.is_valid is True
    assert first_apply.pending_versions == ()
    assert first_apply.applied_versions == second_apply.applied_versions
    assert first_apply.as_dict() == second_apply.as_dict()
