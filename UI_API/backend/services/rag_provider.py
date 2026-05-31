"""RAG Provider — sentence-transformers + ChromaDB

Embedding: shibing624/text2vec-base-chinese（CPU，中文優化）
Vector store: ChromaDB（本地持久化）

切換/停用：config RAG_ENABLED = false
"""
import asyncio
import os
import uuid

import config


class RAGProvider:
    _model = None
    _client = None
    _collection = None

    def _init(self):
        if RAGProvider._model is None:
            from sentence_transformers import SentenceTransformer
            model_name = config.get("RAG_EMBEDDING_MODEL", "shibing624/text2vec-base-chinese")
            print(f"載入 RAG Embedding 模型 ({model_name}, CPU)...")
            RAGProvider._model = SentenceTransformer(model_name, device="cpu")
            print("✅ RAG Embedding 模型載入完成")

        if RAGProvider._collection is None:
            import chromadb
            db_path = os.path.join(config.LEARNING_DATA_DIR, "chroma_rag")
            os.makedirs(db_path, exist_ok=True)
            RAGProvider._client = chromadb.PersistentClient(path=db_path)
            collection_name = config.get("RAG_COLLECTION", "kiosk_rag")
            RAGProvider._collection = RAGProvider._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )

    # ── 查詢 ────────────────────────────────────────────────────────

    async def query(self, text: str, top_k: int | None = None) -> str:
        """查詢相關文件，回傳可注入 LLM prompt 的字串。"""
        if not config.get("RAG_ENABLED", False):
            return ""
        if not text:
            return ""

        self._init()
        k = top_k or int(config.get("RAG_TOP_K", 3))
        threshold = float(config.get("RAG_SCORE_THRESHOLD", 0.5))

        def _run() -> str:
            count = RAGProvider._collection.count()
            if count == 0:
                return ""
            embedding = RAGProvider._model.encode([text])[0].tolist()
            results = RAGProvider._collection.query(
                query_embeddings=[embedding],
                n_results=min(k, count),
                include=["documents", "distances"],
            )
            docs = results.get("documents", [[]])[0]
            dists = results.get("distances", [[]])[0]
            # chromadb cosine distance: 0=完全相同, 1=正交, 2=相反
            # 轉換為相似度 similarity = 1 - distance
            relevant = [
                doc for doc, dist in zip(docs, dists)
                if (1 - dist) >= threshold
            ]
            if not relevant:
                return ""
            return "【RAG 補充資訊】\n" + "\n---\n".join(relevant)

        return await asyncio.to_thread(_run)

    # ── 新增文件 ─────────────────────────────────────────────────────

    async def add_document(
        self,
        content: str,
        source_id: str | None = None,
        source_type: str = "manual",
        metadata: dict | None = None,
    ) -> str:
        """新增或更新文件（同 source_id 覆蓋）。回傳文件 ID。"""
        self._init()
        doc_id = str(source_id or uuid.uuid4())
        meta = {"source_type": source_type, **(metadata or {})}

        def _run() -> str:
            embedding = RAGProvider._model.encode([content])[0].tolist()
            # upsert：先嘗試刪除舊版
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
            return doc_id

        return await asyncio.to_thread(_run)

    # ── 刪除文件 ─────────────────────────────────────────────────────

    async def delete_document(self, doc_id: str) -> bool:
        self._init()
        def _run() -> bool:
            try:
                RAGProvider._collection.delete(ids=[doc_id])
                return True
            except Exception:
                return False
        return await asyncio.to_thread(_run)

    # ── 查詢清單 ─────────────────────────────────────────────────────

    async def list_documents(self) -> list[dict]:
        self._init()
        def _run() -> list[dict]:
            count = RAGProvider._collection.count()
            if count == 0:
                return []
            result = RAGProvider._collection.get(
                include=["documents", "metadatas"]
            )
            return [
                {
                    "id": doc_id,
                    "content": doc,
                    "source_type": (meta or {}).get("source_type", ""),
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

    async def clear_all(self) -> int:
        """清空所有文件。回傳刪除數量。"""
        self._init()
        def _run() -> int:
            n = RAGProvider._collection.count()
            RAGProvider._client.delete_collection(
                config.get("RAG_COLLECTION", "kiosk_rag")
            )
            RAGProvider._collection = None  # 強制重建
            return n
        deleted = await asyncio.to_thread(_run)
        # 重建空 collection
        self._init()
        return deleted


# ── Singleton factory ─────────────────────────────────────────────

_instance: RAGProvider | None = None


def get_rag() -> RAGProvider:
    global _instance
    if _instance is None:
        _instance = RAGProvider()
    return _instance
