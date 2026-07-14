"""Milestone 6A: RAG governance durable repository + content refs."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")


def test_create_draft_stores_object_content_ref(tmp_path, monkeypatch) -> None:
    from services import object_storage_service, rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    object_storage_service.reset_for_tests(backend="local", root=tmp_path / "objs")
    draft = rag_governance_service.create_draft(
        document_id="faq-hours",
        content="Open 09:00-21:00",
        source="manual",
        owner="admin",
        tenant_id=TENANT,
        store_id=STORE,
    )
    assert draft.content_ref.startswith("object:") or draft.content_ref.startswith("inline:")
    assert draft.checksum


def test_rebuild_records_index_version_side_effect(tmp_path, monkeypatch) -> None:
    from services import rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    draft = rag_governance_service.create_draft(
        document_id="faq",
        content="body",
        source="manual",
        owner="admin",
        tenant_id=TENANT,
        store_id=STORE,
    )
    side = rag_governance_service.execute_rebuild_job(
        document_id="faq",
        tenant_id=TENANT,
        store_id=STORE,
    )
    assert side.startswith("rag-rebuild:faq:")
    rows = rag_governance_service._load_assets()
    row = next(r for r in rows if r["document_id"] == "faq" and int(r["version"]) == draft.version)
    assert row.get("index_version")
    assert any(h.get("event") == "rebuild_executed" for h in row.get("history") or [])


def test_json_import_is_idempotent_count_only(tmp_path, monkeypatch) -> None:
    from backend.scripts import import_rag_governance_json
    from repositories import rag_governance_repository
    from services import rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(import_rag_governance_json.config, "LEARNING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rag_governance_repository.config, "LEARNING_DATA_DIR", str(tmp_path))
    # Force JSON path
    monkeypatch.setattr(rag_governance_repository, "use_durable", lambda: False)

    rag_governance_service.create_draft(
        document_id="legacy-1",
        content="hello",
        source="json",
        owner="admin",
        tenant_id=TENANT,
    )
    rows = rag_governance_repository.load_assets()
    report1 = import_rag_governance_json.import_rows(rows, dry_run=False)
    report2 = import_rag_governance_json.import_rows(rows, dry_run=False)
    assert report1["read"] >= 1
    assert report2["skipped"] >= report1["read"]
    assert "content" not in report1
