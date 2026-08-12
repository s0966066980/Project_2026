from __future__ import annotations

from threading import Lock

from modules.runtime_persistence.runtime import sqlite_database_path
from repositories import postgres_utils
from services import llm_routing_service

from .module import AnalyzerRegistry, OptimizationLabModule
from .postgres_store import PostgresOptimizationLabStore
from .sqlite_store import SQLiteOptimizationLabStore

_DEFAULT: OptimizationLabModule | None = None
_KEY: tuple[bool, str] | None = None
_LOCK = Lock()


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
            _DEFAULT = OptimizationLabModule(
                store=store,
                analyzers=AnalyzerRegistry(
                    local_model=str(local_status.get("model") or ""),
                    local_ready=bool(local_status.get("ready")),
                ),
            )
            _KEY = key
        return _DEFAULT


def reset_default_for_tests() -> None:
    global _DEFAULT, _KEY
    with _LOCK:
        _DEFAULT = None
        _KEY = None
