from __future__ import annotations

from threading import Lock

from modules.runtime_persistence.runtime import sqlite_database_path
from repositories import postgres_utils

from .module import VoiceEvidenceModule
from .postgres_store import PostgresVoiceEvidenceStore
from .sqlite_store import SQLiteVoiceEvidenceStore

_DEFAULT: VoiceEvidenceModule | None = None
_KEY: tuple[bool, str] | None = None
_LOCK = Lock()


def default_module() -> VoiceEvidenceModule:
    global _DEFAULT, _KEY
    use_postgres = postgres_utils.use_postgres()
    path = sqlite_database_path()
    key = (use_postgres, path)
    with _LOCK:
        if _DEFAULT is None or _KEY != key:
            store = PostgresVoiceEvidenceStore() if use_postgres else SQLiteVoiceEvidenceStore(path)
            _DEFAULT = VoiceEvidenceModule(store=store)
            _KEY = key
        return _DEFAULT
