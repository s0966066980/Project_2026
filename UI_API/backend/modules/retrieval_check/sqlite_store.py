from __future__ import annotations

import sqlite3
from pathlib import Path

from .sql_store import SQLRetrievalCheckStore


class SQLiteRetrievalCheckStore(SQLRetrievalCheckStore):
    def __init__(self, path: str):
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rag_retrieval_checks (
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    check_id TEXT NOT NULL,
                    index_identity TEXT NOT NULL,
                    configuration_version INTEGER,
                    method TEXT NOT NULL,
                    top_k INTEGER NOT NULL,
                    relevance_policy TEXT NOT NULL,
                    effective_method TEXT NOT NULL,
                    fallback_used TEXT NOT NULL DEFAULT '',
                    result_fingerprint TEXT NOT NULL,
                    result_count INTEGER NOT NULL,
                    eligible INTEGER NOT NULL,
                    eligibility_reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    confirmed_by TEXT,
                    PRIMARY KEY (tenant_id, store_id, check_id)
                );
                CREATE INDEX IF NOT EXISTS idx_rag_retrieval_confirmation
                    ON rag_retrieval_checks (
                        tenant_id, store_id, index_identity,
                        configuration_version, confirmed_at
                    );
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection
