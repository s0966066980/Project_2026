"""Milestone 3C RAG governance contracts."""

from __future__ import annotations

from uuid import UUID

import pytest

TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")


def test_draft_review_publish_and_published_only_retrieval(tmp_path, monkeypatch) -> None:
    from services import rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    draft = rag_governance_service.create_draft(
        document_id="faq-hours",
        content="Open 09:00-21:00",
        source="manual",
        owner="admin",
        tenant_id=TENANT,
        store_id=STORE,
    )
    assert draft.status.value == "draft"
    reviewed = rag_governance_service.submit_for_review("faq-hours", draft.version)
    assert reviewed.status.value == "review"
    published = rag_governance_service.publish("faq-hours", draft.version)
    assert published.status.value == "published"
    assert rag_governance_service.published_only_retrieval_candidates("faq-hours") == ["faq-hours@v1"]


def test_duplicate_checksum_rejected(tmp_path, monkeypatch) -> None:
    from services import rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
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
    from services import rag_governance_service

    monkeypatch.setattr(rag_governance_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    v1 = rag_governance_service.create_draft(
        document_id="menu-note",
        content="v1 content",
        source="menu_supplement",
        owner="admin",
    )
    rag_governance_service.submit_for_review("menu-note", v1.version)
    rag_governance_service.publish("menu-note", v1.version)
    v2 = rag_governance_service.create_draft(
        document_id="menu-note",
        content="v2 content",
        source="menu_supplement",
        owner="admin",
    )
    rag_governance_service.submit_for_review("menu-note", v2.version)
    rag_governance_service.publish("menu-note", v2.version)
    published = rag_governance_service.list_published("menu-note")
    assert len(published) == 1
    assert published[0].version == v2.version
    restored = rag_governance_service.rollback("menu-note", v1.version)
    assert restored.version == v1.version
    assert restored.status.value == "published"
    assert rag_governance_service.published_only_retrieval_candidates("menu-note") == [f"menu-note@v{v1.version}"]


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


def test_rebuild_enqueues_worker_job_with_scope(tmp_path, monkeypatch) -> None:
    from services import rag_governance_service, worker_service

    store = worker_service.InMemoryJobStore()
    job = rag_governance_service.enqueue_rebuild(
        tenant_id=TENANT,
        store_id=STORE,
        document_id="faq-hours",
        store=store,
    )
    assert job["job_type"] == "rag.rebuild"
    assert job["payload_ref"]["document_id"] == "faq-hours"
    assert job["status"] == "pending"


def test_permission_gate_for_publish() -> None:
    from services import rag_governance_service

    rag_governance_service.require_rag_permission("rag.publish", {"rag.publish", "rag.read"})
    with pytest.raises(rag_governance_service.RagGovernanceError):
        rag_governance_service.require_rag_permission("rag.rollback", {"rag.read"})
