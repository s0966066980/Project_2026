import asyncio
from pathlib import Path


class FakeCollection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.deleted_ids = []

    def count(self):
        return len(self.rows)

    def get(self, include):
        return {
            "ids": [row["id"] for row in self.rows],
            "documents": [row["document"] for row in self.rows] if "documents" in include else None,
            "metadatas": [row["metadata"] for row in self.rows] if "metadatas" in include else None,
        }

    def delete(self, ids):
        self.deleted_ids.extend(ids)
        self.rows = [row for row in self.rows if row["id"] not in set(ids)]

    def query(self, query_embeddings, n_results, include):
        ranked = sorted(self.rows, key=lambda row: row.get("dense_rank", 999))[:n_results]
        return {
            "ids": [[row["id"] for row in ranked]],
            "documents": [[row["document"] for row in ranked]],
            "metadatas": [[row["metadata"] for row in ranked]],
            "distances": [[row.get("distance", 0.5) for row in ranked]],
        }


class FakeEmbedding:
    def tolist(self):
        return [0.1, 0.2]


class FakeModel:
    def embed(self, texts):
        return iter([FakeEmbedding()])


class FakeBm25:
    def __init__(self, scores):
        self.scores = scores

    def get_scores(self, tokens):
        return self.scores


def test_required_rag_runtime_dependencies_are_declared():
    requirements = Path(__file__).resolve().parents[1].joinpath("requirements.txt").read_text(encoding="utf-8")
    declared = {line.strip().split("=", 1)[0].lower() for line in requirements.splitlines() if line.strip()}

    assert {"chromadb", "fastembed", "rank-bm25", "jieba"}.issubset(declared)


def test_supported_rag_strategy_names_and_aliases():
    from services.rag_provider import normalize_rag_strategy

    assert normalize_rag_strategy("dense") == "dense"
    assert normalize_rag_strategy("keyword") == "bm25"
    assert normalize_rag_strategy("rrf") == "hybrid_rrf"
    assert normalize_rag_strategy("reranker") == "hybrid_reranker"


def test_search_switches_dense_bm25_and_hybrid_without_changing_interface(tmp_path, monkeypatch):
    from services.rag_provider import RAGProvider

    rows = [
        {"id": "semantic", "document": "早餐供應到十點半", "metadata": {"source_type": "faq"}, "dense_rank": 1, "distance": 0.1},
        {"id": "keyword", "document": "BREAKFAST-1030", "metadata": {"source_type": "policy"}, "dense_rank": 2, "distance": 0.4},
    ]
    collection = FakeCollection(rows)
    monkeypatch.setattr(RAGProvider, "_collection", collection)
    monkeypatch.setattr(RAGProvider, "_model", FakeModel())
    monkeypatch.setattr(RAGProvider, "_bm25", FakeBm25([1.0, 4.0]))
    monkeypatch.setattr(RAGProvider, "_bm25_ids", ["semantic", "keyword"])
    monkeypatch.setattr(RAGProvider, "_bm25_docs", [row["document"] for row in rows])
    monkeypatch.setattr("services.rag_provider.rag_index_selection.read", lambda: (False, []))
    provider = RAGProvider()
    monkeypatch.setattr(provider, "_init", lambda: None)
    monkeypatch.setattr(provider, "_tokenize", lambda text: [text])

    dense = asyncio.run(provider.search("早餐時間", strategy="dense", top_k=2))
    bm25 = asyncio.run(provider.search("早餐時間", strategy="bm25", top_k=2))
    hybrid = asyncio.run(provider.search("早餐時間", strategy="hybrid", top_k=2))

    assert dense["strategy"] == "dense"
    assert [row["id"] for row in dense["results"]] == ["semantic", "keyword"]
    assert [row["id"] for row in bm25["results"]] == ["keyword", "semantic"]
    assert {row["id"] for row in hybrid["results"]} == {"semantic", "keyword"}
    assert all(set(row["match_types"]) == {"dense", "bm25"} for row in hybrid["results"])


def test_scoped_search_only_exposes_artifacts_behind_committed_publication_pointer(monkeypatch):
    from services.rag_provider import RAGProvider

    tenant_id = "00000000-0000-4000-8000-000000000001"
    store_id = "00000000-0000-4000-8000-000000000002"
    rows = [
        {
            "id": "committed",
            "document": "published knowledge",
            "metadata": {
                "tenant_id": tenant_id,
                "store_id": store_id,
                "publication_attempt_id": "pa-committed",
            },
            "dense_rank": 1,
            "distance": 0.1,
        },
        {
            "id": "staged",
            "document": "staged knowledge",
            "metadata": {
                "tenant_id": tenant_id,
                "store_id": store_id,
                "publication_attempt_id": "pa-staged",
            },
            "dense_rank": 2,
            "distance": 0.2,
        },
    ]
    monkeypatch.setattr(RAGProvider, "_collection", FakeCollection(rows))
    monkeypatch.setattr(RAGProvider, "_model", FakeModel())
    monkeypatch.setattr(RAGProvider, "_bm25", None)
    monkeypatch.setattr(RAGProvider, "_bm25_ids", [])
    monkeypatch.setattr(RAGProvider, "_bm25_docs", [])
    monkeypatch.setattr(
        "modules.knowledge_publication.runtime.published_attempt_ids",
        lambda **_scope: {"pa-committed"},
    )
    provider = RAGProvider()
    monkeypatch.setattr(provider, "_init", lambda: None)

    result = asyncio.run(
        provider.search(
            "knowledge",
            strategy="dense",
            top_k=5,
            tenant_id=tenant_id,
            store_id=store_id,
        )
    )

    assert [row["id"] for row in result["results"]] == ["committed"]


def test_query_fails_closed_when_authoritative_selection_is_empty(tmp_path, monkeypatch):
    from services.rag_provider import RAGProvider

    learning_data = tmp_path / "learning_data"
    learning_data.mkdir()
    learning_data.joinpath("rag_index_selection.json").write_text(
        '{"selected_source_ids": []}',
        encoding="utf-8",
    )
    monkeypatch.setattr("services.rag_provider.config.LEARNING_DATA_DIR", str(learning_data))
    monkeypatch.setattr("services.rag_provider.config.get", lambda key, default=None: True if key == "RAG_ENABLED" else default)
    provider = RAGProvider()
    monkeypatch.setattr(provider, "_init", lambda: (_ for _ in ()).throw(AssertionError("Chroma must not be queried")))

    result = asyncio.run(provider.query("舊活動"))

    assert result == ""


def test_query_provider_failure_does_not_block_customer_flow(tmp_path, monkeypatch):
    from services.rag_provider import RAGProvider

    class BrokenCollection:
        def count(self):
            raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(RAGProvider, "_collection", BrokenCollection())
    monkeypatch.setattr("services.rag_provider.config.LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    monkeypatch.setattr("services.rag_provider.config.get", lambda key, default=None: True if key == "RAG_ENABLED" else default)
    provider = RAGProvider()
    monkeypatch.setattr(provider, "_init", lambda: None)

    result = asyncio.run(provider.query("顧客問題"))

    assert result == ""


def test_first_access_prunes_documents_outside_authoritative_selection(tmp_path, monkeypatch):
    from services.rag_provider import RAGProvider

    source_root = tmp_path / "rag_documents"
    source_root.mkdir()
    learning_data = tmp_path / "learning_data"
    learning_data.mkdir()
    learning_data.joinpath("rag_index_selection.json").write_text(
        '{"selected_source_ids": ["keep"]}',
        encoding="utf-8",
    )
    collection = FakeCollection([
        {"id": "keep", "document": "保留", "metadata": {}},
        {"id": "retired", "document": "舊活動", "metadata": {}},
    ])
    monkeypatch.setattr(RAGProvider, "_model", object())
    monkeypatch.setattr(RAGProvider, "_collection", collection)
    monkeypatch.setattr(RAGProvider, "_source_reconciled", False, raising=False)
    monkeypatch.setattr("services.rag_provider.config.RAG_DOCUMENTS_DIR", str(source_root))
    monkeypatch.setattr("services.rag_provider.config.LEARNING_DATA_DIR", str(learning_data))
    provider = RAGProvider()
    monkeypatch.setattr(provider, "_rebuild_bm25", lambda: None)

    documents = asyncio.run(provider.list_documents())

    assert collection.deleted_ids == ["retired"]
    assert [row["id"] for row in documents] == ["keep"]


def test_selection_change_reconciles_an_already_initialized_collection(tmp_path, monkeypatch):
    from services import rag_index_selection
    from services.rag_provider import RAGProvider

    source_root = tmp_path / "rag_documents"
    source_root.mkdir()
    learning_data = tmp_path / "learning_data"
    learning_data.mkdir()
    monkeypatch.setattr("services.rag_index_selection.config.LEARNING_DATA_DIR", str(learning_data))
    rag_index_selection.write(["keep", "retired"])
    collection = FakeCollection([
        {"id": "keep", "document": "保留", "metadata": {}},
        {"id": "retired", "document": "下架", "metadata": {}},
    ])
    monkeypatch.setattr(RAGProvider, "_model", object())
    monkeypatch.setattr(RAGProvider, "_collection", collection)
    monkeypatch.setattr(RAGProvider, "_source_reconciled", False, raising=False)
    monkeypatch.setattr(RAGProvider, "_source_selection_state", None, raising=False)
    monkeypatch.setattr("services.rag_provider.config.RAG_DOCUMENTS_DIR", str(source_root))
    monkeypatch.setattr("services.rag_provider.config.LEARNING_DATA_DIR", str(learning_data))
    provider = RAGProvider()
    monkeypatch.setattr(provider, "_rebuild_bm25", lambda: None)

    asyncio.run(provider.list_documents())
    rag_index_selection.write(["keep"])
    documents = asyncio.run(provider.list_documents())

    assert collection.deleted_ids == ["retired"]
    assert [row["id"] for row in documents] == ["keep"]


def test_first_access_preserves_path_documents_when_source_root_is_unavailable(tmp_path, monkeypatch):
    from services.rag_provider import RAGProvider

    collection = FakeCollection([
        {"id": "source", "document": "保留", "metadata": {"path": "faq/keep.md"}},
    ])
    monkeypatch.setattr(RAGProvider, "_model", object())
    monkeypatch.setattr(RAGProvider, "_collection", collection)
    monkeypatch.setattr(RAGProvider, "_source_reconciled", False, raising=False)
    monkeypatch.setattr("services.rag_provider.config.RAG_DOCUMENTS_DIR", str(tmp_path / "unmounted"))
    monkeypatch.setattr("services.rag_provider.config.LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    provider = RAGProvider()
    monkeypatch.setattr(provider, "_rebuild_bm25", lambda: None)

    documents = asyncio.run(provider.list_documents())

    assert collection.deleted_ids == []
    assert [row["id"] for row in documents] == ["source"]


def test_collection_name_preserves_runtime_settings_compatibility(monkeypatch):
    from services.rag_provider import RAGProvider

    monkeypatch.setattr(
        "services.rag_provider.config.get",
        lambda key, default=None: "legacy_runtime_collection" if key == "RAG_COLLECTION" else default,
    )

    assert RAGProvider._collection_name() == "legacy_runtime_collection"


def test_first_access_prunes_indexed_documents_whose_source_file_was_removed(tmp_path, monkeypatch):
    from services.rag_provider import RAGProvider

    source_root = tmp_path / "rag_documents"
    (source_root / "faq").mkdir(parents=True)
    (source_root / "faq" / "keep.md").write_text("保留", encoding="utf-8")
    collection = FakeCollection([
        {"id": "keep", "document": "保留", "metadata": {"path": "faq/keep.md"}},
        {"id": "retired", "document": "舊活動", "metadata": {"path": "promotions/deleted.json"}},
        {"id": "direct", "document": "直接建立", "metadata": {}},
    ])
    monkeypatch.setattr(RAGProvider, "_model", object())
    monkeypatch.setattr(RAGProvider, "_collection", collection)
    monkeypatch.setattr(RAGProvider, "_source_reconciled", False, raising=False)
    monkeypatch.setattr("services.rag_provider.config.RAG_DOCUMENTS_DIR", str(source_root))
    provider = RAGProvider()
    monkeypatch.setattr(provider, "_rebuild_bm25", lambda: None)

    documents = asyncio.run(provider.list_documents())

    assert collection.deleted_ids == ["retired"]
    assert [row["id"] for row in documents] == ["keep", "direct"]
