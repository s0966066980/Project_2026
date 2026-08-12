from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.postgres]
MIGRATION = Path(__file__).resolve().parents[1] / "backend/schemas/migrations/0028_optimization_lab.sql"


def test_optimization_migration_creates_scoped_reference_only_tables():
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "optimization_evidence",
        "optimization_snapshots",
        "optimization_reports",
        "optimization_egress_audits",
        "optimization_access_audits",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "audio_ref" not in sql
    assert "member_id" not in sql
    assert "order_id" not in sql
    assert "payment_id" not in sql
    assert "expires_at" in sql


def test_optimization_migration_has_no_production_mutation_surface():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "settings" not in sql
    assert "campaign" not in sql
    assert "recommendation" not in sql
    assert "rag_publications" not in sql
