from __future__ import annotations

import hashlib
import json
from threading import Lock

from modules.runtime_persistence.runtime import sqlite_database_path

import config
from repositories import postgres_utils

from .module import RetrievalCheckModule, RetrievalIdentity
from .postgres_store import PostgresRetrievalCheckStore
from .sqlite_store import SQLiteRetrievalCheckStore


class ProductionRetrievalEngine:
    async def retrieve(self, *, scope, query, method, top_k, relevance_policy):
        from services import rag_knowledge_service

        return await rag_knowledge_service.test_retrieval(
            scope=scope,
            query=query,
            method=method,
            top_k=top_k,
            relevance_policy=relevance_policy,
            fallback_enabled=True,
            record_online_health=False,
        )


class ProductionRetrievalIdentityProvider:
    def current(self, *, scope) -> RetrievalIdentity:
        from modules.knowledge_publication import runtime as publication_runtime

        from services import rag_knowledge_service

        attempts = sorted(publication_runtime.default_module().published_attempt_ids(scope=scope))
        index_identity = hashlib.sha256(
            json.dumps(
                {
                    "index_format": rag_knowledge_service.INDEX_VERSION,
                    "published_attempt_ids": attempts,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        configuration = rag_knowledge_service.list_configurations(scope).get("published")
        return RetrievalIdentity(
            index_identity=index_identity,
            configuration_version=(int(configuration["version"]) if configuration is not None else None),
            configuration=configuration,
        )


_DEFAULT: RetrievalCheckModule | None = None
_KEY: tuple[bool, str] | None = None
_LOCK = Lock()


def default_module() -> RetrievalCheckModule:
    global _DEFAULT, _KEY
    use_postgres = postgres_utils.use_postgres()
    path = sqlite_database_path()
    key = (use_postgres, path)
    with _LOCK:
        if _DEFAULT is None or _KEY != key:
            store = PostgresRetrievalCheckStore() if use_postgres else SQLiteRetrievalCheckStore(path)
            _DEFAULT = RetrievalCheckModule(
                store=store,
                engine=ProductionRetrievalEngine(),
                identities=ProductionRetrievalIdentityProvider(),
                pending_ttl_seconds=int(config.get("RAG_RETRIEVAL_CHECK_TTL_SECONDS", 900)),
            )
            _KEY = key
        return _DEFAULT


def reset_default_for_tests() -> None:
    global _DEFAULT, _KEY
    with _LOCK:
        _DEFAULT = None
        _KEY = None
