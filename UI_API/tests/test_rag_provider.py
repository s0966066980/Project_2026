import asyncio


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
