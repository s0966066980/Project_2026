"""Milestone 3C RAG governance contracts."""

from __future__ import annotations

from uuid import UUID

import pytest

TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")


def test_draft_review_publish_and_published_only_retrieval(tmp_path, monkeypatch) -> None:
    from services import object_storage_service, rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rag_governance_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    object_storage_service.reset_for_tests(backend="local", root=tmp_path / "objects")
    draft = rag_governance_service.create_draft(
        document_id="faq-hours",
        content="Open 09:00-21:00",
        source="manual",
        owner="admin",
        tenant_id=TENANT,
        store_id=STORE,
    )
    assert draft.status.value == "draft"
    with pytest.raises(rag_governance_service.RagGovernanceError, match="invalid_publish_status"):
        rag_governance_service.publish("faq-hours", draft.version)
    reviewed = rag_governance_service.submit_for_review("faq-hours", draft.version)
    assert reviewed.status.value == "review"
    approved = rag_governance_service.approve("faq-hours", draft.version)
    assert approved.status.value == "approved"
    published = rag_governance_service.publish("faq-hours", draft.version)
    assert published.status.value == "published"
    assert rag_governance_service.published_only_retrieval_candidates("faq-hours") == ["faq-hours@v1"]
    source = tmp_path / "rag_documents" / "manual" / "faq-hours.json"
    assert source.is_file()
    assert "Open 09:00-21:00" in source.read_text(encoding="utf-8")


def test_duplicate_checksum_rejected(tmp_path, monkeypatch) -> None:
    from services import object_storage_service, rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    object_storage_service.reset_for_tests(backend="local", root=tmp_path / "objects")
    rag_governance_service.create_draft(
        document_id="policy-a",
        content="same-body",
        source="policy",
        owner="admin",
    )
    with pytest.raises(rag_governance_service.RagGovernanceError):
        rag_governance_service.create_draft(
            document_id="policy-a",
            content="same-body",
            source="policy",
            owner="admin",
        )


def test_publish_supersedes_previous_and_rollback_restores(tmp_path, monkeypatch) -> None:
    from services import object_storage_service, rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rag_governance_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    object_storage_service.reset_for_tests(backend="local", root=tmp_path / "objects")
    v1 = rag_governance_service.create_draft(
        document_id="menu-note",
        content="v1 content",
        source="menu_supplement",
        owner="admin",
    )
    rag_governance_service.submit_for_review("menu-note", v1.version)
    rag_governance_service.approve("menu-note", v1.version)
    rag_governance_service.publish("menu-note", v1.version)
    v2 = rag_governance_service.create_draft(
        document_id="menu-note",
        content="v2 content",
        source="menu_supplement",
        owner="admin",
    )
    rag_governance_service.submit_for_review("menu-note", v2.version)
    rag_governance_service.approve("menu-note", v2.version)
    rag_governance_service.publish("menu-note", v2.version)
    published = rag_governance_service.list_published("menu-note")
    assert len(published) == 1
    assert published[0].version == v2.version
    restored = rag_governance_service.rollback("menu-note", v1.version)
    assert restored.version == v1.version
    assert restored.status.value == "published"
    assert rag_governance_service.published_only_retrieval_candidates("menu-note") == [f"menu-note@v{v1.version}"]
    source = tmp_path / "rag_documents" / "menu" / "menu-note.json"
    assert "v1 content" in source.read_text(encoding="utf-8")


def test_rejected_version_is_terminal_and_correction_creates_new_draft(tmp_path, monkeypatch) -> None:
    from services import object_storage_service, rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    object_storage_service.reset_for_tests(backend="local", root=tmp_path / "objects")
    draft = rag_governance_service.create_draft(
        document_id="faq-payment",
        content="cash only",
        source="faq",
        owner="admin",
    )
    rag_governance_service.submit_for_review("faq-payment", draft.version)
    rejected = rag_governance_service.reject(
        "faq-payment",
        draft.version,
        reason="missing card details",
    )
    assert rejected.status.value == "rejected"
    with pytest.raises(rag_governance_service.RagGovernanceError, match="invalid_approved_status"):
        rag_governance_service.approve("faq-payment", draft.version)

    corrected = rag_governance_service.create_draft(
        document_id="faq-payment",
        content="cash and card",
        source="faq",
        owner="admin",
    )
    assert corrected.version == 2
    assert corrected.status.value == "draft"


def test_retrieval_trace_records_versions_and_scores() -> None:
    from services import rag_governance_service

    trace = rag_governance_service.build_retrieval_trace(
        query_ref="q-123",
        hits=[
            {"document_id": "faq-hours", "version": 2, "chunk_id": "c1", "score": 0.91},
            {"document_id": "policy-a", "version": 1, "chunk_id": "c9", "score": 0.44},
        ],
        provider="chroma",
        latency_ms=12.5,
    )
    assert trace.query_ref == "q-123"
    assert trace.document_versions == ["faq-hours@v2", "policy-a@v1"]
    assert trace.chunk_ids == ["c1", "c9"]
    assert trace.scores[0] == pytest.approx(0.91)
    assert trace.provider == "chroma"


def test_legacy_rebuild_job_is_not_available_after_studio_cutover(tmp_path, monkeypatch) -> None:
    from services import rag_document_service, worker_service

    store = worker_service.InMemoryJobStore()
    with pytest.raises(ValueError, match="Unsupported job type: rag.rebuild"):
        rag_document_service.enqueue_rebuild(
            tenant_id=TENANT,
            store_id=STORE,
            selected_source_ids=["faq-hours"],
            store=store,
        )


def test_permission_gate_for_publish() -> None:
    from services import rag_governance_service

    rag_governance_service.require_rag_permission("rag.publish", {"rag.publish", "rag.read"})
    with pytest.raises(rag_governance_service.RagGovernanceError):
        rag_governance_service.require_rag_permission("rag.rollback", {"rag.read"})
