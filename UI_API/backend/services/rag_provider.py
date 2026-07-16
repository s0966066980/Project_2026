"""RAG Provider — Hybrid Search（Dense + BM25 + RRF）

Pipeline:
  1. Dense Vector Search  — fastembed + ChromaDB（語意相近）
  2. BM25 Sparse Search   — rank-bm25 + jieba 斷詞（精確關鍵字）
  3. RRF Fusion           — Reciprocal Rank Fusion 合併排序（k=60）
  4. 注入 LLM prompt

安裝依賴：pip install fastembed chromadb rank-bm25 jieba
切換/停用：config RAG_ENABLED = false

fastembed 優點：不依賴 transformers/PyTorch，安裝乾淨，用 ONNX 執行。
"""
import asyncio
import os
import uuid
from pathlib import Path

import config


class RAGProvider:
    _model = None       # SentenceTransformer
    _client = None      # ChromaDB PersistentClient
    _collection = None  # ChromaDB Collection
    _source_reconciled = False

    # BM25 in-memory index（從 ChromaDB 同步重建）
    _bm25 = None
    _bm25_ids: list = []
    _bm25_docs: list = []

    # ── 初始化 ────────────────────────────────────────────────────

    def _init(self):
        """懶初始化：載入 Embedding 模型與 ChromaDB，並重建 BM25 index。"""
        if RAGProvider._model is None:
            from fastembed import TextEmbedding
            model_name = config.get("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
            print(f"載入 RAG Embedding 模型 ({model_name}, ONNX/CPU)...")
            RAGProvider._model = TextEmbedding(model_name=model_name)
            print("✅ RAG Embedding 模型載入完成")

        if RAGProvider._collection is None:
            import chromadb
            db_path = config.RAG_CHROMA_DIR
            os.makedirs(db_path, exist_ok=True)
            RAGProvider._client = chromadb.PersistentClient(path=db_path)
            collection_name = config.RAG_COLLECTION
            RAGProvider._collection = RAGProvider._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )

        if not RAGProvider._source_reconciled:
            self._prune_missing_source_documents()
            RAGProvider._source_reconciled = True
            # ChromaDB reconciliation 後立即同步 BM25。
            self._rebuild_bm25()

    def _prune_missing_source_documents(self) -> int:
        """Remove indexed source files that no longer exist; preserve direct-write documents."""
        root = Path(config.RAG_DOCUMENTS_DIR)
        if not root.is_absolute():
            root = Path(config.PROJECT_DIR) / root
        root = root.resolve()
        result = RAGProvider._collection.get(include=["metadatas"])
        orphaned_ids = []
        for doc_id, metadata in zip(result.get("ids", []), result.get("metadatas", [])):
            relative_path = str((metadata or {}).get("path") or "").strip()
            if not relative_path:
                continue
            source_path = (root / relative_path).resolve()
            try:
                source_path.relative_to(root)
            except ValueError:
                orphaned_ids.append(doc_id)
                continue
            if not source_path.is_file():
                orphaned_ids.append(doc_id)
        if orphaned_ids:
            RAGProvider._collection.delete(ids=orphaned_ids)
        return len(orphaned_ids)

    # ── BM25 工具 ─────────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """jieba 斷詞，讓 BM25 正確處理中文。"""
        try:
            import jieba
            return list(jieba.cut(text))
        except ImportError:
            # jieba 未安裝時退化為字元分割
            return list(text)

    def _rebuild_bm25(self):
        """從 ChromaDB 現有文件重建 BM25 in-memory index。同步執行。"""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            print("⚠️ rank-bm25 未安裝，跳過 BM25 index 建立")
            return

        count = RAGProvider._collection.count()
        if count == 0:
            RAGProvider._bm25 = None
            RAGProvider._bm25_ids = []
            RAGProvider._bm25_docs = []
            return

        result = RAGProvider._collection.get(include=["documents"])
        ids = result.get("ids", [])
        docs = result.get("documents", [])
        tokenized = [self._tokenize(doc) for doc in docs]
        RAGProvider._bm25 = BM25Okapi(tokenized)
        RAGProvider._bm25_ids = list(ids)
        RAGProvider._bm25_docs = list(docs)

    # ── RRF 融合 ──────────────────────────────────────────────────

    @staticmethod
    def _rrf(dense_ids: list[str], bm25_ids: list[str], k: int = 60) -> list[str]:
        """Reciprocal Rank Fusion：合併兩組排名，回傳依 RRF 分數排序的 ID 清單。"""
        scores: dict[str, float] = {}
        for rank, doc_id in enumerate(dense_ids):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        for rank, doc_id in enumerate(bm25_ids):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        return sorted(scores, key=lambda x: scores[x], reverse=True)

    # ── 查詢（Hybrid） ────────────────────────────────────────────

    async def query(self, text: str, top_k: int | None = None) -> str:
        """Hybrid Search：Dense + BM25 + RRF → 回傳可注入 LLM 的 context 字串。"""
        if not config.get("RAG_ENABLED", False):
            return ""
        if not text:
            return ""

        self._init()
        k = top_k or int(config.get("RAG_TOP_K", 3))
        fetch_k = k * 2  # 每路多取一些再融合

        def _run() -> str:
            count = RAGProvider._collection.count()
            if count == 0:
                return ""

            n = min(fetch_k, count)

            # ── Dense Search ──
            embedding = next(RAGProvider._model.embed([text])).tolist()
            dense_results = RAGProvider._collection.query(
                query_embeddings=[embedding],
                n_results=n,
                include=["documents", "distances"],
            )
            dense_ids: list[str] = dense_results.get("ids", [[]])[0]
            dense_doc_map: dict[str, str] = {
                doc_id: doc
                for doc_id, doc in zip(
                    dense_ids,
                    dense_results.get("documents", [[]])[0],
                )
            }

            # ── BM25 Search ──
            bm25_ids: list[str] = []
            if RAGProvider._bm25 is not None and RAGProvider._bm25_ids:
                tokens = self._tokenize(text)
                scores = RAGProvider._bm25.get_scores(tokens)
                ranked = sorted(
                    range(len(RAGProvider._bm25_ids)),
                    key=lambda i: scores[i],
                    reverse=True,
                )[:n]
                # 過濾掉 BM25 分數為 0 的結果（完全無關鍵字命中）
                bm25_ids = [
                    RAGProvider._bm25_ids[i]
                    for i in ranked
                    if scores[i] > 0
                ]

            # ── RRF Fusion ──
            fused_ids = self._rrf(dense_ids, bm25_ids)[:k]

            # ── 收集文件 ──
            # 合併 dense 和 BM25 的文件 map（BM25 可能返回 dense 沒有的結果）
            all_doc_map: dict[str, str] = {
                doc_id: doc
                for doc_id, doc in zip(
                    RAGProvider._bm25_ids,
                    RAGProvider._bm25_docs,
                )
            }
            all_doc_map.update(dense_doc_map)

            relevant = [
                all_doc_map[doc_id]
                for doc_id in fused_ids
                if doc_id in all_doc_map
            ]

            if not relevant:
                return ""
            return "【RAG 補充資訊】\n" + "\n---\n".join(relevant)

        return await asyncio.to_thread(_run)

    # ── 新增文件 ─────────────────────────────────────────────────

    async def add_document(
        self,
        content: str,
        source_id: str | None = None,
        source_type: str = "manual",
        metadata: dict | None = None,
    ) -> str:
        """新增或更新文件（同 source_id 覆蓋）。同步更新 BM25 index。"""
        self._init()
        doc_id = str(source_id or uuid.uuid4())
        meta = {"source_type": source_type, **(metadata or {})}

        def _run() -> str:
            embedding = next(RAGProvider._model.embed([content])).tolist()
            try:
                RAGProvider._collection.delete(ids=[doc_id])
            except Exception:
                pass
            RAGProvider._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[meta],
            )
            # 同步重建 BM25（小資料集，重建很快）
            self._rebuild_bm25()
            return doc_id

        return await asyncio.to_thread(_run)

    # ── 刪除文件 ─────────────────────────────────────────────────

    async def delete_document(self, doc_id: str) -> bool:
        self._init()

        def _run() -> bool:
            try:
                RAGProvider._collection.delete(ids=[doc_id])
                self._rebuild_bm25()
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_run)

    # ── 查詢清單 ─────────────────────────────────────────────────

    async def list_documents(self) -> list[dict]:
        self._init()

        def _run() -> list[dict]:
            count = RAGProvider._collection.count()
            if count == 0:
                return []
            result = RAGProvider._collection.get(include=["documents", "metadatas"])
            return [
                {
                    "id": doc_id,
                    "content": doc,
                    "source_type": (meta or {}).get("source_type", ""),
                    "metadata": dict(meta or {}),
                }
                for doc_id, doc, meta in zip(
                    result.get("ids", []),
                    result.get("documents", []),
                    result.get("metadatas", []),
                )
            ]

        return await asyncio.to_thread(_run)

    async def count(self) -> int:
        self._init()
        return await asyncio.to_thread(lambda: RAGProvider._collection.count())

    # ── 清空 ────────────────────────────────────────────────────

    async def clear_all(self) -> int:
        self._init()

        def _run() -> int:
            n = RAGProvider._collection.count()
            collection_name = config.RAG_COLLECTION
            RAGProvider._client.delete_collection(collection_name)
            RAGProvider._collection = None
            RAGProvider._source_reconciled = False
            RAGProvider._bm25 = None
            RAGProvider._bm25_ids = []
            RAGProvider._bm25_docs = []
            return n

        deleted = await asyncio.to_thread(_run)
        self._init()  # 重建空 collection
        return deleted


# ── Singleton ────────────────────────────────────────────────────

_instance: RAGProvider | None = None


def get_rag() -> RAGProvider:
    global _instance
    if _instance is None:
        _instance = RAGProvider()
    return _instance
