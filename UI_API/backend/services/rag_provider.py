"""RAG Provider — shared multi-method retrieval index.

Strategies:
  - dense: fastembed + ChromaDB semantic similarity
  - bm25: rank-bm25 + jieba exact keyword retrieval
  - hybrid_rrf: both rankings combined with Reciprocal Rank Fusion
  - hybrid_reranker: RRF candidates reordered by a deterministic reranker preset

安裝依賴：pip install fastembed chromadb rank-bm25 jieba
切換：config RAG_STRATEGY；停用：config RAG_ENABLED = false

fastembed 優點：不依賴 transformers/PyTorch，安裝乾淨，用 ONNX 執行。
"""

import asyncio
import logging
import os
import threading
import uuid
from pathlib import Path

import config
from models.commercial_scope import CommercialScope
from services import rag_index_selection

logger = logging.getLogger(__name__)

RAG_STRATEGIES = ("dense", "bm25", "hybrid_rrf", "hybrid_reranker")


def normalize_rag_strategy(value: object) -> str:
    """Return a supported retrieval strategy or reject an invalid explicit value."""
    normalized = str(value or "").strip().lower()
    aliases = {
        "vector": "dense",
        "keyword": "bm25",
        "rrf": "hybrid_rrf",
        "hybrid": "hybrid_rrf",
        "reranker": "hybrid_reranker",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in RAG_STRATEGIES:
        raise ValueError(f"unsupported RAG strategy: {normalized or '(empty)'}")
    return normalized


class RAGProvider:
    _model = None  # SentenceTransformer
    _client = None  # ChromaDB PersistentClient
    _collection = None  # ChromaDB Collection
    _source_reconciled = False
    _source_selection_state: tuple[bool, tuple[str, ...]] | None = None

    # BM25 in-memory index（從 ChromaDB 同步重建）
    _bm25 = None
    _bm25_ids: list = []
    _bm25_docs: list = []
    _init_lock = threading.Lock()

    # ── 初始化 ────────────────────────────────────────────────────

    @staticmethod
    def _collection_name() -> str:
        return str(config.get("RAG_COLLECTION", config.RAG_COLLECTION) or config.RAG_COLLECTION)

    def _init(self):
        """懶初始化：載入 Embedding 模型與 ChromaDB，並重建 BM25 index。"""
        with RAGProvider._init_lock:
            self._init_locked()

    def _init_locked(self):
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
            collection_name = self._collection_name()
            RAGProvider._collection = RAGProvider._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )

        selection_configured, selected_source_ids = rag_index_selection.read()
        selection_state = (selection_configured, tuple(selected_source_ids))
        if not RAGProvider._source_reconciled or RAGProvider._source_selection_state != selection_state:
            self._prune_missing_source_documents(selection_configured, selected_source_ids)
            RAGProvider._source_reconciled = True
            RAGProvider._source_selection_state = selection_state
            # ChromaDB reconciliation 後立即同步 BM25。
            self._rebuild_bm25()

    def _prune_missing_source_documents(
        self,
        selection_configured: bool | None = None,
        selected_source_ids: list[str] | None = None,
    ) -> int:
        """Remove documents outside the authoritative selection or with missing source files."""
        root = Path(config.RAG_DOCUMENTS_DIR)
        if not root.is_absolute():
            root = Path(config.PROJECT_DIR) / root
        root = root.resolve()
        source_root_available = root.is_dir() and os.access(root, os.R_OK)
        result = RAGProvider._collection.get(include=["metadatas"])
        if selection_configured is None or selected_source_ids is None:
            selection_configured, selected_source_ids = rag_index_selection.read()
        selected = set(selected_source_ids)
        orphaned_ids = []
        for doc_id, metadata in zip(result.get("ids", []), result.get("metadatas", [])):
            # Studio knowledge is governed by its published-version pointer and
            # must never be pruned by the retired filesystem source selection.
            if str((metadata or {}).get("knowledge_item_id") or ""):
                continue
            if str((metadata or {}).get("source_type") or "") == "faq":
                orphaned_ids.append(doc_id)
                continue
            if selection_configured and doc_id not in selected:
                orphaned_ids.append(doc_id)
                continue
            relative_path = str((metadata or {}).get("path") or "").strip()
            if not relative_path or not source_root_available:
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
            from rank_bm25 import BM25Plus
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
        # BM25Okapi produces non-positive IDF scores for a one-document corpus,
        # which makes a valid first Knowledge Item impossible to retrieve.
        RAGProvider._bm25 = BM25Plus(tokenized)
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

    @staticmethod
    def _configured_strategy() -> str:
        try:
            return normalize_rag_strategy(config.get("RAG_STRATEGY", "hybrid_rrf"))
        except ValueError:
            logger.warning("Invalid RAG_STRATEGY setting; falling back to hybrid_rrf")
            return "hybrid_rrf"

    def _search_sync(
        self,
        text: str,
        top_k: int,
        strategy: str,
        tenant_id: str = "",
        store_id: str = "",
    ) -> list[dict]:
        self._init()
        count = RAGProvider._collection.count()
        if count == 0:
            return []

        scoped = bool(tenant_id or store_id)
        hybrid = strategy in {"hybrid_rrf", "hybrid_reranker"}
        fetch_k = count if scoped else (top_k * 4 if hybrid else top_k)
        n = min(fetch_k, count)
        all_rows = RAGProvider._collection.get(include=["documents", "metadatas"])
        all_ids = list(all_rows.get("ids", []))
        doc_map = dict(zip(all_ids, all_rows.get("documents", [])))
        metadata_map = {
            doc_id: dict(metadata or {}) for doc_id, metadata in zip(all_ids, all_rows.get("metadatas", []))
        }
        published_attempts: set[str] = set()
        if scoped:
            try:
                from capabilities.knowledge_rag import knowledge_publication_runtime

                published_attempts = knowledge_publication_runtime.published_attempt_ids(
                    tenant_id=tenant_id,
                    store_id=store_id,
                )
            except Exception:
                # New publication artifacts fail closed if durable visibility
                # cannot be resolved; legacy documents have no attempt marker.
                published_attempts = set()
        allowed_ids = {
            doc_id
            for doc_id, metadata in metadata_map.items()
            if (not tenant_id or str(metadata.get("tenant_id") or "") == tenant_id)
            and (not store_id or str(metadata.get("store_id") or "") == store_id)
            and (
                not str(metadata.get("publication_attempt_id") or "")
                or str(metadata.get("publication_attempt_id")) in published_attempts
            )
        }

        dense_ids: list[str] = []
        dense_scores: dict[str, float] = {}
        if strategy in {"dense", "hybrid_rrf", "hybrid_reranker"}:
            embedding = next(RAGProvider._model.embed([text])).tolist()
            dense_results = RAGProvider._collection.query(
                query_embeddings=[embedding],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )
            dense_ids = list(dense_results.get("ids", [[]])[0])
            for doc_id, document in zip(dense_ids, dense_results.get("documents", [[]])[0]):
                doc_map[doc_id] = document
            for doc_id, metadata in zip(dense_ids, dense_results.get("metadatas", [[]])[0]):
                metadata_map[doc_id] = dict(metadata or {})
            for doc_id, distance in zip(dense_ids, dense_results.get("distances", [[]])[0]):
                try:
                    dense_scores[doc_id] = max(0.0, 1.0 - float(distance))
                except (TypeError, ValueError):
                    continue
            dense_ids = [doc_id for doc_id in dense_ids if doc_id in allowed_ids]

        bm25_ids: list[str] = []
        bm25_scores: dict[str, float] = {}
        if (
            strategy in {"bm25", "hybrid_rrf", "hybrid_reranker"}
            and RAGProvider._bm25 is not None
            and RAGProvider._bm25_ids
        ):
            scores = RAGProvider._bm25.get_scores(self._tokenize(text))
            ranked = sorted(
                range(len(RAGProvider._bm25_ids)),
                key=lambda index: scores[index],
                reverse=True,
            )[:n]
            for index in ranked:
                score = float(scores[index])
                if score <= 0:
                    continue
                doc_id = RAGProvider._bm25_ids[index]
                if doc_id not in allowed_ids:
                    continue
                bm25_ids.append(doc_id)
                bm25_scores[doc_id] = score

        if strategy == "dense":
            ranked_ids = dense_ids
        elif strategy == "bm25":
            ranked_ids = bm25_ids
        else:
            ranked_ids = self._rrf(dense_ids, bm25_ids)
            if strategy == "hybrid_reranker":
                query_tokens = set(self._tokenize(text.casefold()))

                def rerank_score(doc_id: str) -> tuple[float, float]:
                    document_tokens = set(self._tokenize(str(doc_map.get(doc_id) or "").casefold()))
                    lexical_overlap = len(query_tokens & document_tokens) / max(1, len(query_tokens))
                    semantic = dense_scores.get(doc_id, 0.0)
                    keyword = bm25_scores.get(doc_id, 0.0)
                    normalized_keyword = keyword / (1.0 + keyword)
                    return (
                        0.45 * semantic + 0.35 * lexical_overlap + 0.20 * normalized_keyword,
                        -ranked_ids.index(doc_id),
                    )

                ranked_ids = sorted(ranked_ids, key=rerank_score, reverse=True)
        ranked_ids = ranked_ids[:top_k]

        results = []
        for rank, doc_id in enumerate(ranked_ids, start=1):
            if doc_id not in doc_map:
                continue
            metadata = metadata_map.get(doc_id, {})
            match_types = []
            if doc_id in dense_ids:
                match_types.append("dense")
            if doc_id in bm25_ids:
                match_types.append("bm25")
            if strategy == "dense":
                score = dense_scores.get(doc_id)
            elif strategy == "bm25":
                score = bm25_scores.get(doc_id)
            elif strategy == "hybrid_rrf":
                score = sum(1.0 / (60 + ids.index(doc_id) + 1) for ids in (dense_ids, bm25_ids) if doc_id in ids)
            else:
                query_tokens = set(self._tokenize(text.casefold()))
                document_tokens = set(self._tokenize(str(doc_map.get(doc_id) or "").casefold()))
                overlap = len(query_tokens & document_tokens) / max(1, len(query_tokens))
                keyword = bm25_scores.get(doc_id, 0.0)
                score = 0.45 * dense_scores.get(doc_id, 0.0) + 0.35 * overlap + 0.20 * (keyword / (1.0 + keyword))
            results.append(
                {
                    "rank": rank,
                    "id": doc_id,
                    "content": str(doc_map[doc_id] or ""),
                    "source_type": str(metadata.get("source_type") or ""),
                    "metadata": metadata,
                    "match_types": match_types,
                    "score": round(float(score), 6) if score is not None else None,
                }
            )
        return results

    async def search(
        self,
        text: str,
        top_k: int | None = None,
        strategy: str | None = None,
        tenant_id: str = "",
        store_id: str = "",
    ) -> dict:
        """Search indexed documents for Admin previews and internal query composition.

        This does not inspect RAG_ENABLED: an Admin may preview retrieval before enabling
        RAG. Authoritative source selection is still enforced.
        """
        query_text = str(text or "").strip()
        resolved_strategy = normalize_rag_strategy(strategy) if strategy is not None else self._configured_strategy()
        requested_k = int(top_k or config.get("RAG_TOP_K", 3) or 3)
        resolved_k = max(1, min(requested_k, 10))
        if not query_text:
            return {"strategy": resolved_strategy, "results": [], "total": 0}

        results = await asyncio.to_thread(
            self._search_sync,
            query_text,
            resolved_k,
            resolved_strategy,
            str(tenant_id or ""),
            str(store_id or ""),
        )
        return {"strategy": resolved_strategy, "results": results, "total": len(results)}

    # ── 正式查詢 ─────────────────────────────────────────────────

    async def query(
        self,
        text: str,
        top_k: int | None = None,
        *,
        scope: CommercialScope | None = None,
    ) -> str:
        """Use the configured strategy and return the existing LLM context contract."""
        if not config.get("RAG_ENABLED", False):
            return ""
        if not text:
            return ""

        try:
            payload = await self.search(
                text,
                top_k=top_k,
                tenant_id=str(scope.tenant_id) if scope else "",
                store_id=str(scope.store_id) if scope else "",
            )
            relevant = [str(row.get("content") or "") for row in payload["results"] if row.get("content")]
            if not relevant:
                return ""
            return "【RAG 補充資訊】\n" + "\n---\n".join(relevant)
        except Exception:
            # RAG is optional; never log the customer query or let provider failures block checkout.
            logger.exception("RAG query failed; continuing without supplemental context")
            return ""

    # ── 新增文件 ─────────────────────────────────────────────────

    async def add_document(
        self,
        content: str,
        source_id: str | None = None,
        source_type: str = "manual",
        metadata: dict | None = None,
    ) -> str:
        """新增或更新文件（同 source_id 覆蓋）。同步更新 BM25 index。"""
        await asyncio.to_thread(self._init)
        doc_id = str(source_id or uuid.uuid4())
        meta = {"source_type": source_type, **(metadata or {})}

        def _run() -> str:
            embedding = next(RAGProvider._model.embed([content])).tolist()
            RAGProvider._collection.upsert(
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
        await asyncio.to_thread(self._init)

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
        await asyncio.to_thread(self._init)

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
        await asyncio.to_thread(self._init)
        return await asyncio.to_thread(lambda: RAGProvider._collection.count())

    # ── 清空 ────────────────────────────────────────────────────

    async def clear_all(self) -> int:
        await asyncio.to_thread(self._init)

        def _run() -> int:
            n = RAGProvider._collection.count()
            collection_name = self._collection_name()
            RAGProvider._client.delete_collection(collection_name)
            RAGProvider._collection = None
            RAGProvider._source_reconciled = False
            RAGProvider._source_selection_state = None
            RAGProvider._bm25 = None
            RAGProvider._bm25_ids = []
            RAGProvider._bm25_docs = []
            return n

        deleted = await asyncio.to_thread(_run)
        await asyncio.to_thread(self._init)  # 重建空 collection
        return deleted


# ── Singleton ────────────────────────────────────────────────────

_instance: RAGProvider | None = None


def get_rag() -> RAGProvider:
    global _instance
    if _instance is None:
        _instance = RAGProvider()
    return _instance
