from __future__ import annotations

import sqlite3
from pathlib import Path

from .sql_store import SQLRetrievalConfigurationStore


class SQLiteRetrievalConfigurationStore(SQLRetrievalConfigurationStore):
    def __init__(self, path: str):
        self._path = str(path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS retrieval_configurations (
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    method TEXT NOT NULL CHECK (method IN ('bm25', 'dense', 'hybrid_rrf', 'hybrid_reranker')),
                    top_k INTEGER NOT NULL CHECK (top_k IN (3, 5, 10)),
                    relevance_policy TEXT NOT NULL CHECK (relevance_policy IN ('lenient', 'balanced', 'strict')),
                    preset_version TEXT NOT NULL,
                    index_version TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    published_by TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, store_id)
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
