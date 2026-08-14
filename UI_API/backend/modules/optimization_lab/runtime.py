from __future__ import annotations

from threading import Lock

from modules.operations import _llm_routing as llm_routing_service
from modules.runtime_persistence.runtime import sqlite_database_path
from repositories import postgres_utils

from .module import AnalyzerRegistry, OptimizationLabModule
from .postgres_store import PostgresOptimizationLabStore
from .sqlite_store import SQLiteOptimizationLabStore

_DEFAULT: OptimizationLabModule | None = None
_KEY: tuple[bool, str] | None = None
_LOCK = Lock()


class _KnowledgePublicationAdapter:
    """Application-owned adapter at the Optimization → Knowledge seam."""

    def __init__(self, module):
        self._module = module

    def list_items(self, *, scope):
        return self._module.list_items(scope=scope)

    def get_item(self, *, scope, item_id):
        return self._module.get_item(scope=scope, item_id=item_id)

    def create_draft(self, **kwargs):
        return self._module.create_draft(**kwargs)

    def revise_draft(self, **kwargs):
        return self._module.revise_draft(**kwargs)

    def request_publication(self, **kwargs):
        return self._module.request_publication(**kwargs)


def default_module() -> OptimizationLabModule:
    global _DEFAULT, _KEY
    use_postgres = postgres_utils.use_postgres()
    path = sqlite_database_path()
    key = (use_postgres, path)
    with _LOCK:
        if _DEFAULT is None or _KEY != key:
            store = PostgresOptimizationLabStore() if use_postgres else SQLiteOptimizationLabStore(path)
            try:
                local_status = llm_routing_service.readiness()["local"]
            except Exception:
                local_status = {"model": "", "ready": False}
            from modules.knowledge_publication import runtime as knowledge_runtime
            from modules.voice_evidence import runtime as voice_evidence_runtime

            _DEFAULT = OptimizationLabModule(
                store=store,
                analyzers=AnalyzerRegistry(
                    local_model=str(local_status.get("model") or ""),
                    local_ready=bool(local_status.get("ready")),
                ),
                knowledge=_KnowledgePublicationAdapter(knowledge_runtime.default_module()),
                evidence_capability=voice_evidence_runtime.default_module(),
            )
            _KEY = key
        return _DEFAULT


def reset_default_for_tests() -> None:
    global _DEFAULT, _KEY
    with _LOCK:
        _DEFAULT = None
        _KEY = None
