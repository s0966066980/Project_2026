"""The retained RAG configuration and ad hoc retrieval test flows.

Knowledge publication is owned by ``modules.knowledge_publication`` and
retrieval checks by ``modules.retrieval_check``. This service is deliberately
small: it owns only the published retrieval method and the provider adapter
needed by the ad hoc check.
"""

from __future__ import annotations

import json
import time
from threading import Lock
from typing import Any

from modules.retrieval_configuration import (
    INDEX_VERSION as _INDEX_VERSION,
)
from modules.retrieval_configuration import (
    METHODS,
    PRESET_VERSION,
    RELEVANCE_POLICIES,
    TOP_K_VALUES,
    RetrievalConfigurationError,
    RetrievalConfigurationModule,
)
from modules.retrieval_configuration.postgres_store import PostgresRetrievalConfigurationStore
from modules.retrieval_configuration.sqlite_store import SQLiteRetrievalConfigurationStore
from modules.runtime_persistence.runtime import sqlite_database_path

import config
from models.commercial_scope import CommercialScope
from repositories import postgres_utils
from services.rag_provider import get_rag

CHUNKING_VERSION = "content-aware-2026.1"
INDEX_VERSION = _INDEX_VERSION
POLICY_THRESHOLDS = {
    "bm25": {"lenient": 0.05, "balanced": 0.20, "strict": 0.50},
    "dense": {"lenient": 0.30, "balanced": 0.45, "strict": 0.60},
    "hybrid_rrf": {"lenient": 0.012, "balanced": 0.016, "strict": 0.025},
    "hybrid_reranker": {"lenient": 0.20, "balanced": 0.30, "strict": 0.50},
}


class RagKnowledgeError(ValueError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


class RagKnowledgeConflictError(RagKnowledgeError):
    pass


_CONFIGURATION: RetrievalConfigurationModule | None = None
_CONFIGURATION_KEY: tuple[bool, str] | None = None
_CONFIGURATION_LOCK = Lock()
_VISIBLE_PUBLICATION_TOKENS: dict[tuple[str, str], frozenset[str]] = {}


def _configuration_module() -> RetrievalConfigurationModule:
    global _CONFIGURATION, _CONFIGURATION_KEY
    use_postgres = postgres_utils.use_postgres()
    sqlite_path = sqlite_database_path()
    key = (use_postgres, sqlite_path)
    with _CONFIGURATION_LOCK:
        if _CONFIGURATION is None or _CONFIGURATION_KEY != key:
            store = (
                PostgresRetrievalConfigurationStore()
                if use_postgres
                else SQLiteRetrievalConfigurationStore(sqlite_path)
            )
            _CONFIGURATION = RetrievalConfigurationModule(store=store)
            _CONFIGURATION_KEY = key
        return _CONFIGURATION


def reset_configuration_for_tests() -> None:
    global _CONFIGURATION, _CONFIGURATION_KEY
    with _CONFIGURATION_LOCK:
        _CONFIGURATION = None
        _CONFIGURATION_KEY = None


def reset_runtime_index_visibility_for_tests() -> None:
    _VISIBLE_PUBLICATION_TOKENS.clear()


async def ensure_published_index_visible(
    *,
    scope: CommercialScope,
    publication_module: Any | None = None,
    provider: Any | None = None,
) -> None:
    """Read-repair worker publications into the querying process.

    Chroma's embedded persistent client does not refresh a process-local segment
    after another process writes it. Publication remains a worker job, but the
    first query after the durable published-attempt token changes idempotently
    upserts those exact artifacts in the app process before retrieval.
    """

    if publication_module is None:
        from modules.knowledge_publication.runtime import default_module

        publication_module = default_module()
    active_provider = provider or get_rag()
    token = frozenset(publication_module.published_attempt_ids(scope=scope))
    scope_key = (str(scope.tenant_id), str(scope.store_id))
    if _VISIBLE_PUBLICATION_TOKENS.get(scope_key) == token:
        return

    items = publication_module.list_items(scope=scope).get("items", [])
    for item in items:
        if item.get("published_version") is None:
            continue
        pointer = publication_module.get_published(scope=scope, item_id=str(item["item_id"]))
        attempt_id = str(pointer.get("attempt_id") or "")
        if attempt_id not in token:
            continue
        try:
            document_ids = json.loads(str(pointer.get("artifact_ref") or ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RagKnowledgeError("published_index_artifact_invalid") from exc
        chunks = list(item.get("chunks") or [])
        if not isinstance(document_ids, list) or len(document_ids) != len(chunks):
            raise RagKnowledgeError("published_index_artifact_invalid")
        for chunk, document_id in zip(chunks, document_ids):
            await active_provider.add_document(
                str(chunk.get("content") or ""),
                source_id=str(document_id),
                source_type=str(item.get("content_type") or "knowledge_article"),
                metadata={
                    "tenant_id": scope_key[0],
                    "store_id": scope_key[1],
                    "knowledge_item_id": str(item["item_id"]),
                    "knowledge_version": int(item["published_version"]),
                    "publication_attempt_id": attempt_id,
                    "category": str(item.get("category") or "other"),
                    "title": str(item.get("title") or ""),
                    "index_version": INDEX_VERSION,
                    "chunking_version": CHUNKING_VERSION,
                    "embedding_version": str(config.get("RAG_EMBEDDING_MODEL", "default")),
                    "reranker_version": str(config.get("RAG_RERANKER_MODEL", "default")),
                    "preset_version": PRESET_VERSION,
                },
            )
    _VISIBLE_PUBLICATION_TOKENS[scope_key] = token


def list_configurations(scope: CommercialScope) -> dict[str, Any]:
    return _configuration_module().list(scope=scope)


def publish_configuration(
    *,
    scope: CommercialScope,
    method: str,
    top_k: int,
    relevance_policy: str,
    actor: str,
    source_version: int | None = None,
) -> dict[str, Any]:
    try:
        return _configuration_module().publish(
            scope=scope,
            method=method,
            top_k=top_k,
            relevance_policy=relevance_policy,
            actor=actor,
            source_version=source_version,
        )
    except RetrievalConfigurationError as exc:
        raise RagKnowledgeError(exc.code) from exc


def delete_configuration(*, scope: CommercialScope, version: int, actor: str) -> dict[str, Any]:
    try:
        return _configuration_module().delete(scope=scope, version=version, actor=actor)
    except RetrievalConfigurationError as exc:
        raise RagKnowledgeError(exc.code) from exc


def _published_config(scope: CommercialScope) -> dict[str, Any] | None:
    return list_configurations(scope).get("published")


def _filter_retrieval_rows(
    result: dict[str, Any], *, method: str, policy: str
) -> tuple[list[dict[str, Any]], float]:
    threshold = POLICY_THRESHOLDS[method][policy]
    rows: list[dict[str, Any]] = []
    for hit in result.get("results") or []:
        try:
            if hit.get("score") is None or float(hit["score"]) < threshold:
                continue
        except (TypeError, ValueError):
            continue
        metadata = dict(hit.get("metadata") or {})
        rows.append(
            {
                **hit,
                "rank": len(rows) + 1,
                "item_id": metadata.get("knowledge_item_id", ""),
                "title": metadata.get("title", ""),
                "category": metadata.get("category", ""),
                "content_type": metadata.get("content_type", hit.get("source_type", "")),
                "chunk_id": metadata.get("chunk_id", ""),
            }
        )
    return rows, threshold


async def test_retrieval(
    *,
    scope: CommercialScope,
    query: str,
    method: str | None = None,
    top_k: int | None = None,
    relevance_policy: str | None = None,
    expected_knowledge_ids: list[str] | None = None,
    fallback_enabled: bool = True,
    record_online_health: bool = False,
) -> dict[str, Any]:
    """Run one retrieval call against the published configuration.

    ``record_online_health`` remains accepted by the provider seam for callers
    outside the retained surface, but P1 no longer stores online query history.
    """

    config = _published_config(scope) or {
        "method": "hybrid_rrf",
        "top_k": 5,
        "relevance_policy": "balanced",
        "version": None,
    }
    selected_method = str(method or config["method"])
    if selected_method not in {str(row["id"]) for row in METHODS}:
        raise RagKnowledgeError("invalid_retrieval_method")
    selected_k = int(top_k or config["top_k"])
    if selected_k not in TOP_K_VALUES:
        raise RagKnowledgeError("invalid_top_k")
    policy = str(relevance_policy or config["relevance_policy"])
    if policy not in RELEVANCE_POLICIES:
        raise RagKnowledgeError("invalid_relevance_policy")

    started = time.perf_counter()
    await ensure_published_index_visible(scope=scope)
    chains = {
        "bm25": ["bm25"],
        "dense": ["dense", "bm25"],
        "hybrid_rrf": ["hybrid_rrf", "bm25"],
        "hybrid_reranker": ["hybrid_reranker", "hybrid_rrf", "bm25"],
    }
    attempts = chains[selected_method] if fallback_enabled else [selected_method]
    last_error: Exception | None = None
    result: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    threshold = POLICY_THRESHOLDS[selected_method][policy]
    effective_method = selected_method
    fallback_used = ""
    for attempt in attempts:
        try:
            candidate = await get_rag().search(
                str(query or "").strip(),
                strategy=attempt,
                top_k=selected_k,
                tenant_id=str(scope.tenant_id),
                store_id=str(scope.store_id),
            )
            candidate_rows, candidate_threshold = _filter_retrieval_rows(
                candidate, method=attempt, policy=policy
            )
            result = candidate
            rows = candidate_rows
            threshold = candidate_threshold
            effective_method = attempt
            if attempt != selected_method:
                fallback_used = attempt
            if rows or attempt == attempts[-1]:
                break
        except Exception as exc:
            last_error = exc
    if result is None:
        raise last_error or RagKnowledgeError("retrieval_unavailable")

    ranks = [
        int(row["rank"])
        for row in rows
        if row.get("item_id") in set(expected_knowledge_ids or [])
    ]
    return {
        "method": selected_method,
        "effective_method": effective_method,
        "top_k": selected_k,
        "relevance_policy": policy,
        "relevance_threshold": threshold,
        "fallback_used": fallback_used,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "results": rows,
        "total": len(rows),
        "expected_hit": None if not expected_knowledge_ids else bool(ranks),
        "expected_rank": min(ranks) if ranks else None,
    }
