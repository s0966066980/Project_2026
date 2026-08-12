from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[1] / "backend/schemas/migrations/0027_remove_pre_pilot_rag_history.sql"


def test_p1_migration_moves_active_config_before_dropping_old_aggregate():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS retrieval_configurations" in sql
    assert "FROM rag_studio_states" in sql
    assert "INSERT INTO rag_reset_receipts" in sql
    assert "DROP TABLE IF EXISTS rag_studio_states" in sql


def test_p1_migration_does_not_drop_retained_rag_state():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS rag_retrieval_checks" not in sql
    assert "DROP TABLE IF EXISTS knowledge_items" not in sql
    assert "DROP TABLE IF EXISTS knowledge_versions" not in sql
    assert "DROP TABLE IF EXISTS publication_attempts" not in sql


def test_pre_pilot_worker_names_are_gone_from_runtime_contracts():
    worker_jobs = (Path(__file__).resolve().parents[1] / "backend/models/worker_jobs.py").read_text(encoding="utf-8")
    worker_handlers = (Path(__file__).resolve().parents[1] / "backend/services/worker_handlers.py").read_text(
        encoding="utf-8"
    )

    assert "rag.studio.evaluate" not in worker_jobs
    assert "rag.studio.evaluate" not in worker_handlers
    assert "knowledge.publication.index" in worker_jobs
    assert "handle_knowledge_publication_index" in worker_handlers
