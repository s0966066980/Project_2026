from __future__ import annotations

import sqlite3
from pathlib import Path

from .sql_store import SQLOptimizationLabStore


class SQLiteOptimizationLabStore(SQLOptimizationLabStore):
    def __init__(self, path: str | Path):
        self._path = str(path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS optimization_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    transcript_masked TEXT NOT NULL,
                    assistant_text_masked TEXT NOT NULL,
                    rag_hit TEXT NOT NULL,
                    voice_outcome TEXT NOT NULL,
                    failure_type TEXT NOT NULL,
                    retry_outcome TEXT NOT NULL,
                    synthetic INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS optimization_evidence_scope_time
                    ON optimization_evidence (tenant_id, store_id, observed_at);
                CREATE TABLE IF NOT EXISTS optimization_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    store_date TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    cutoff_at TEXT NOT NULL,
                    partial INTEGER NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS optimization_reports (
                    report_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    analyzer_id TEXT NOT NULL,
                    analyzer_version TEXT NOT NULL,
                    model TEXT NOT NULL,
                    effort TEXT NOT NULL,
                    data_scope TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS optimization_egress_audits (
                    audit_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    analyzer_id TEXT NOT NULL,
                    analyzer_version TEXT NOT NULL,
                    model TEXT NOT NULL,
                    effort TEXT NOT NULL,
                    data_scope TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    authorization_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS optimization_access_audits (
                    audit_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    step_up_expires_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL
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
