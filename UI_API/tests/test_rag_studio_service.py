import asyncio
from uuid import uuid4

import pytest

import config
from models.commercial_scope import CommercialScope
from models.worker_jobs import ALLOWED_JOB_TYPES
from repositories import postgres_utils
from services import rag_knowledge_service
from services.rag_provider import normalize_rag_strategy


@pytest.fixture
def scope(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LEARNING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(postgres_utils, "use_postgres", lambda: False)
    return CommercialScope(tenant_id=uuid4(), store_id=uuid4())


def test_studio_exposes_fixed_categories_content_types_and_methods():
    metadata = rag_knowledge_service.metadata()

    assert len(metadata["categories"]) == 9
    assert {row["id"] for row in metadata["content_types"]} == {
        "knowledge_article",
        "question_answer",
        "policy_rule",
        "operating_procedure",
    }
    assert {row["id"] for row in metadata["methods"]} == {
        "bm25",
        "dense",
        "hybrid_rrf",
        "hybrid_reranker",
    }




def test_retrieval_configuration_is_immutable_and_rollback_creates_new_version(scope):
    first = rag_knowledge_service.publish_configuration(
        scope=scope,
        method="hybrid_rrf",
        top_k=5,
        relevance_policy="balanced",
        actor="publisher",
    )
    second = rag_knowledge_service.publish_configuration(
        scope=scope,
        method="dense",
        top_k=3,
        relevance_policy="strict",
        actor="publisher",
    )
    restored = rag_knowledge_service.publish_configuration(
        scope=scope,
        method="bm25",
        top_k=10,
        relevance_policy="lenient",
        source_version=first["version"],
        actor="publisher",
    )

    assert [first["version"], second["version"], restored["version"]] == [1, 2, 3]
    assert restored["method"] == "hybrid_rrf"
    assert restored["restored_from_version"] == 1
    assert rag_knowledge_service.list_configurations(scope)["published"]["version"] == 3


def test_any_retrieval_configuration_can_be_deleted_without_reusing_version(scope):
    first = rag_knowledge_service.publish_configuration(
        scope=scope,
        method="hybrid_rrf",
        top_k=5,
        relevance_policy="balanced",
        actor="publisher",
    )
    current = rag_knowledge_service.publish_configuration(
        scope=scope,
        method="dense",
        top_k=3,
        relevance_policy="strict",
        actor="publisher",
    )

    deleted = rag_knowledge_service.delete_configuration(
        scope=scope,
        version=first["version"],
        actor="admin",
    )
    assert deleted["deleted_version"] == 1
    assert [row["version"] for row in rag_knowledge_service.list_configurations(scope)["configurations"]] == [2]

    deleted_current = rag_knowledge_service.delete_configuration(
        scope=scope,
        version=current["version"],
        actor="admin",
    )
    assert deleted_current["was_published"] is True
    assert rag_knowledge_service.list_configurations(scope) == {
        "configurations": [],
        "published": None,
    }

    next_config = rag_knowledge_service.publish_configuration(
        scope=scope,
        method="bm25",
        top_k=10,
        relevance_policy="lenient",
        actor="publisher",
    )
    assert next_config["version"] == 3


def test_new_worker_and_strategy_contracts_replace_legacy_names():
    assert "rag.studio.index" in ALLOWED_JOB_TYPES
    assert "rag.studio.evaluate" in ALLOWED_JOB_TYPES
    assert "rag.rebuild" not in ALLOWED_JOB_TYPES
    assert normalize_rag_strategy("hybrid") == "hybrid_rrf"
    assert normalize_rag_strategy("reranker") == "hybrid_reranker"


def test_balanced_hybrid_rrf_keeps_a_top_single_channel_match(scope, monkeypatch):
    class SingleChannelRag:
        async def search(self, *_args, **_kwargs):
            return {
                "results": [
                    {
                        "id": "chunk-1",
                        "content": "會員享九折優惠。",
                        "source_type": "policy_rule",
                        "metadata": {
                            "knowledge_item_id": "ki_1",
                            "title": "會員優惠",
                            "category": "membership",
                            "content_type": "policy_rule",
                            "chunk_id": "chunk-1",
                        },
                        "match_types": ["dense"],
                        "score": 1 / 61,
                    }
                ]
            }

    monkeypatch.setattr(rag_knowledge_service, "get_rag", lambda: SingleChannelRag())

    result = asyncio.run(
        rag_knowledge_service.test_retrieval(
            scope=scope,
            query="會員有什麼折扣？",
            method="hybrid_rrf",
            top_k=5,
            relevance_policy="balanced",
            record_online_health=False,
        )
    )

    assert result["total"] == 1


def test_balanced_reranker_keeps_a_calibrated_natural_language_match(scope, monkeypatch):
    class CalibratedRag:
        async def search(self, *_args, **_kwargs):
            return {
                "results": [
                    {
                        "id": "chunk-1",
                        "content": "會員消費可享九折優惠。",
                        "source_type": "policy_rule",
                        "metadata": {
                            "knowledge_item_id": "ki_1",
                            "title": "會員9折",
                            "category": "membership",
                            "content_type": "policy_rule",
                            "chunk_id": "chunk-1",
                        },
                        "match_types": ["dense"],
                        "score": 0.32,
                    }
                ]
            }

    monkeypatch.setattr(rag_knowledge_service, "get_rag", lambda: CalibratedRag())

    result = asyncio.run(
        rag_knowledge_service.test_retrieval(
            scope=scope,
            query="會員有什麼優惠？",
            method="hybrid_reranker",
            top_k=5,
            relevance_policy="balanced",
            fallback_enabled=False,
        )
    )

    assert result["total"] == 1
    assert result["effective_method"] == "hybrid_reranker"
    assert result["fallback_used"] == ""


def test_zero_result_after_policy_filter_uses_next_retrieval_strategy(scope, monkeypatch):
    calls = []

    class FallbackRag:
        async def search(self, *_args, strategy, **_kwargs):
            calls.append(strategy)
            score = 0.29 if strategy == "hybrid_reranker" else 1 / 61
            return {
                "results": [
                    {
                        "id": "chunk-1",
                        "content": "會員消費可享九折優惠。",
                        "source_type": "policy_rule",
                        "metadata": {
                            "knowledge_item_id": "ki_1",
                            "title": "會員9折",
                            "category": "membership",
                            "content_type": "policy_rule",
                            "chunk_id": "chunk-1",
                        },
                        "match_types": [strategy],
                        "score": score,
                    }
                ]
            }

    monkeypatch.setattr(rag_knowledge_service, "get_rag", lambda: FallbackRag())

    result = asyncio.run(
        rag_knowledge_service.test_retrieval(
            scope=scope,
            query="會員有什麼優惠？",
            method="hybrid_reranker",
            top_k=5,
            relevance_policy="balanced",
        )
    )

    assert calls == ["hybrid_reranker", "hybrid_rrf"]
    assert result["total"] == 1
    assert result["effective_method"] == "hybrid_rrf"
    assert result["fallback_used"] == "hybrid_rrf"
