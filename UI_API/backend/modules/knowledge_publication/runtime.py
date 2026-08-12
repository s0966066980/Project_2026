from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import config
from models.commercial_scope import CommercialScope
from modules.operations import _worker as worker_service
from modules.runtime_persistence.runtime import sqlite_database_path
from repositories import postgres_utils
from services.rag_provider import get_rag

from .module import KnowledgePublicationModule, TransientPublicationError
from .postgres_store import PostgresPublicationStore
from .sqlite_store import SQLitePublicationStore

INDEX_VERSION = "shared-multi-method-2026.1"
CHUNKING_VERSION = "content-aware-2026.1"
PRESET_VERSION = "rag-preset-2026.1"


class WorkerPublicationJobs:
    def enqueue(self, *, attempt_id: str, scope: CommercialScope) -> str:
        job = worker_service.enqueue_job(
            tenant_id=scope.tenant_id,
            store_id=scope.store_id,
            job_type="knowledge.publication.index",
            payload_ref={"attempt_id": attempt_id},
            idempotency_key=f"knowledge-publication:{scope.store_id}:{attempt_id}",
            max_attempts=3,
        )
        return str(job.job_id)


class RagPublicationArtifacts:
    def __init__(self, provider=None):
        self._provider = provider or get_rag()

    @staticmethod
    def _versions() -> dict[str, str]:
        return {
            "index_version": INDEX_VERSION,
            "chunking_version": CHUNKING_VERSION,
            "embedding_version": str(config.get("RAG_EMBEDDING_MODEL", "default")),
            "reranker_version": str(config.get("RAG_RERANKER_MODEL", "default")),
            "preset_version": PRESET_VERSION,
        }

    def build(self, *, attempt: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        document_ids: list[str] = []
        try:
            for chunk in item["chunks"]:
                document_id = f"kp:{attempt['attempt_id']}:{chunk['chunk_id']}"
                document_ids.append(document_id)
                asyncio.run(
                    self._provider.add_document(
                        chunk["content"],
                        source_id=document_id,
                        source_type=item["content_type"],
                        metadata={
                            "tenant_id": str(attempt.get("tenant_id") or ""),
                            "store_id": str(attempt.get("store_id") or ""),
                            "knowledge_item_id": item["item_id"],
                            "knowledge_version": item["version"],
                            "publication_attempt_id": attempt["attempt_id"],
                            "category": item["category"],
                            "title": item["title"],
                            **self._versions(),
                        },
                    )
                )
        except Exception as exc:
            for document_id in reversed(document_ids):
                try:
                    asyncio.run(self._provider.delete_document(document_id))
                except Exception:
                    pass
            raise TransientPublicationError(str(exc)) from exc
        return {
            "artifact_ref": json.dumps(document_ids, separators=(",", ":")),
            "document_ids": document_ids,
            "content_checksum": item["checksum"],
            **self._versions(),
        }

    def cleanup(self, *, artifact_ref: str) -> None:
        try:
            document_ids = json.loads(artifact_ref)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("invalid_publication_artifact_ref") from exc
        for document_id in document_ids:
            if not asyncio.run(self._provider.delete_document(str(document_id))):
                raise TransientPublicationError("artifact_cleanup_failed")

    def is_compatible(self, *, artifact: dict[str, Any], item: dict[str, Any]) -> bool:
        expected = self._versions()
        return bool(
            artifact.get("artifact_ref")
            and artifact.get("content_checksum") == item["checksum"]
            and all(artifact.get(key) == value for key, value in expected.items())
        )


_DEFAULT: KnowledgePublicationModule | None = None
_DEFAULT_KEY: tuple[bool, str] | None = None
_LOCK = Lock()


def default_module() -> KnowledgePublicationModule:
    global _DEFAULT, _DEFAULT_KEY
    use_postgres = postgres_utils.use_postgres()
    sqlite_path = sqlite_database_path()
    key = (use_postgres, sqlite_path)
    with _LOCK:
        if _DEFAULT is None or _DEFAULT_KEY != key:
            store = PostgresPublicationStore() if use_postgres else SQLitePublicationStore(sqlite_path)
            _DEFAULT = KnowledgePublicationModule(
                store=store,
                jobs=WorkerPublicationJobs(),
                artifacts=RagPublicationArtifacts(),
            )
            _DEFAULT_KEY = key
        return _DEFAULT


def published_attempt_ids(*, tenant_id: str, store_id: str) -> set[str]:
    if not tenant_id or not store_id:
        return set()
    from uuid import UUID

    scope = CommercialScope(tenant_id=UUID(tenant_id), store_id=UUID(store_id))
    return default_module().published_attempt_ids(scope=scope)


def cleanup_expired_artifacts(*, days: int | None = None) -> dict[str, Any]:
    retention_days = int(days if days is not None else config.get("KNOWLEDGE_ARTIFACT_RETENTION_DAYS", 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))).isoformat()
    return default_module().cleanup_expired_artifacts(cutoff=cutoff)


def reset_default_for_tests() -> None:
    global _DEFAULT, _DEFAULT_KEY
    with _LOCK:
        _DEFAULT = None
        _DEFAULT_KEY = None
