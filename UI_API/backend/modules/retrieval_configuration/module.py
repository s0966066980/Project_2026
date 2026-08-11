from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from models.commercial_scope import CommercialScope


class RetrievalConfigurationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class RetrievalConfigurationStore(Protocol):
    def get(self, *, scope: CommercialScope) -> dict[str, Any] | None: ...

    def save(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]: ...

    def delete(self, *, scope: CommercialScope, version: int) -> dict[str, Any]: ...


METHODS: tuple[dict[str, Any], ...] = (
    {
        "id": "bm25",
        "label": "BM25 關鍵字",
        "use_case": "品名、代碼、時間與精確字詞",
        "limitation": "不擅長同義詞與口語改寫",
    },
    {
        "id": "dense",
        "label": "Dense 語意向量",
        "use_case": "自然語句、同義詞與口語問法",
        "limitation": "精確代碼或罕見名稱可能較弱",
    },
    {
        "id": "hybrid_rrf",
        "label": "Hybrid RRF",
        "use_case": "兼顧關鍵字與語意的一般門市問答",
        "limitation": "融合排序不會重新理解候選內容",
        "recommended_baseline": True,
    },
    {
        "id": "hybrid_reranker",
        "label": "Hybrid + Reranker",
        "use_case": "高準確度、內容相近的知識集合",
        "limitation": "延遲與運算成本較高",
    },
)
METHOD_IDS = {str(row["id"]) for row in METHODS}
TOP_K_VALUES = (3, 5, 10)
RELEVANCE_POLICIES = ("lenient", "balanced", "strict")
PRESET_VERSION = "rag-preset-2026.1"
INDEX_VERSION = "shared-multi-method-2026.1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RetrievalConfigurationModule:
    def __init__(self, *, store: RetrievalConfigurationStore):
        self._store = store

    def list(self, *, scope: CommercialScope) -> dict[str, Any]:
        current = self._store.get(scope=scope)
        return {"configurations": [current] if current else [], "published": current}

    def publish(
        self,
        *,
        scope: CommercialScope,
        method: str,
        top_k: int,
        relevance_policy: str,
        actor: str,
        source_version: int | None = None,
    ) -> dict[str, Any]:
        current = self._store.get(scope=scope)
        if source_version is not None:
            if current is None or int(current["version"]) != int(source_version):
                raise RetrievalConfigurationError("configuration_not_found")
            method = str(current["method"])
            top_k = int(current["top_k"])
            relevance_policy = str(current["relevance_policy"])
        method = str(method or "").strip()
        if method not in METHOD_IDS:
            raise RetrievalConfigurationError("invalid_retrieval_method")
        if int(top_k) not in TOP_K_VALUES:
            raise RetrievalConfigurationError("invalid_top_k")
        relevance_policy = str(relevance_policy or "").strip()
        if relevance_policy not in RELEVANCE_POLICIES:
            raise RetrievalConfigurationError("invalid_relevance_policy")
        version = int(current["version"]) + 1 if current else 1
        return self._store.save(
            scope=scope,
            record={
                "version": version,
                "status": "published",
                "method": method,
                "top_k": int(top_k),
                "relevance_policy": relevance_policy,
                "preset_version": PRESET_VERSION,
                "index_version": INDEX_VERSION,
                "published_at": _now(),
                "published_by": str(actor or "admin"),
            },
        )

    def delete(self, *, scope: CommercialScope, version: int, actor: str) -> dict[str, Any]:
        current = self._store.get(scope=scope)
        if current is None or int(current["version"]) != int(version):
            raise RetrievalConfigurationError("configuration_not_found")
        deleted = self._store.delete(scope=scope, version=int(version))
        return {
            **deleted,
            "deleted_by": str(actor or "admin"),
            "deleted_at": _now(),
        }
