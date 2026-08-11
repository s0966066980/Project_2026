"""Regression tests for worker-to-app RAG index visibility."""

import asyncio
from types import SimpleNamespace
from uuid import UUID

from models.commercial_scope import CommercialScope
from services import rag_knowledge_service
from services.rag_provider import RAGProvider

SCOPE = CommercialScope(
    tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
    store_id=UUID("00000000-0000-4000-8000-000000000002"),
)


class _PublicationModule:
    def published_attempt_ids(self, *, scope):
        assert scope == SCOPE
        return {"attempt-1"}

    def list_items(self, *, scope):
        assert scope == SCOPE
        return {
            "items": [
                {
                    "item_id": "item-1",
                    "version": 1,
                    "published_version": 1,
                    "content_type": "knowledge_article",
                    "category": "store_and_hours",
                    "title": "早餐供應時間",
                    "chunks": [{"chunk_id": "item-1:v1:c1", "content": "早餐供應到十點半。"}],
                }
            ]
        }

    def get_published(self, *, scope, item_id):
        assert scope == SCOPE
        assert item_id == "item-1"
        return {
            "attempt_id": "attempt-1",
            "artifact_ref": '["kp:attempt-1:item-1:v1:c1"]',
        }


class _Provider:
    def __init__(self):
        self.added = []

    async def add_document(self, content, *, source_id, source_type, metadata):
        self.added.append((content, source_id, source_type, metadata))
        return source_id


def test_published_index_is_read_repaired_once_per_visibility_token(monkeypatch):
    rag_knowledge_service.reset_runtime_index_visibility_for_tests()
    monkeypatch.setattr(rag_knowledge_service.config, "get", lambda _key, default=None: default)
    provider = _Provider()
    publication = _PublicationModule()

    asyncio.run(
        rag_knowledge_service.ensure_published_index_visible(
            scope=SCOPE,
            publication_module=publication,
            provider=provider,
        )
    )
    asyncio.run(
        rag_knowledge_service.ensure_published_index_visible(
            scope=SCOPE,
            publication_module=publication,
            provider=provider,
        )
    )

    assert len(provider.added) == 1
    content, source_id, source_type, metadata = provider.added[0]
    assert content == "早餐供應到十點半。"
    assert source_id == "kp:attempt-1:item-1:v1:c1"
    assert source_type == "knowledge_article"
    assert metadata["publication_attempt_id"] == "attempt-1"
    assert metadata["knowledge_item_id"] == "item-1"


def test_provider_document_write_is_an_idempotent_upsert(monkeypatch):
    provider = RAGProvider()
    calls = []

    class _Collection:
        def upsert(self, **kwargs):
            calls.append(kwargs)

        def count(self):
            return 0

    monkeypatch.setattr(provider, "_init", lambda: None)
    monkeypatch.setattr(provider, "_rebuild_bm25", lambda: None)
    monkeypatch.setattr(RAGProvider, "_collection", _Collection())
    monkeypatch.setattr(
        RAGProvider,
        "_model",
        SimpleNamespace(embed=lambda _texts: iter([SimpleNamespace(tolist=lambda: [0.1, 0.2])])),
    )

    asyncio.run(provider.add_document("內容", source_id="stable-id", metadata={"title": "標題"}))

    assert calls == [
        {
            "ids": ["stable-id"],
            "embeddings": [[0.1, 0.2]],
            "documents": ["內容"],
            "metadatas": [{"source_type": "manual", "title": "標題"}],
        }
    ]
