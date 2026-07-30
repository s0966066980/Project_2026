from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from models.commercial_scope import CommercialScope

from .module import PublicationError

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS knowledge_items (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    category TEXT NOT NULL,
    content_type TEXT NOT NULL,
    row_revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, item_id)
);

CREATE TABLE IF NOT EXISTS knowledge_versions (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'draft', 'indexing', 'published', 'index_failed',
        'publication_failed', 'retired'
    )),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_checksum TEXT NOT NULL,
    chunks_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    published_at TEXT,
    PRIMARY KEY (tenant_id, store_id, item_id, version),
    FOREIGN KEY (tenant_id, store_id, item_id)
        REFERENCES knowledge_items (tenant_id, store_id, item_id)
);

CREATE TABLE IF NOT EXISTS publication_batches (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, batch_id)
);

CREATE TABLE IF NOT EXISTS publication_attempts (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('build', 'swap', 'cleanup', 'complete')),
    status TEXT NOT NULL CHECK (status IN (
        'in_progress', 'cleanup_pending', 'index_failed', 'publication_failed', 'published'
    )),
    job_id TEXT,
    artifact_ref TEXT,
    cleanup_artifact_ref TEXT,
    artifact_manifest_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    safe_reason TEXT,
    retry_eligible INTEGER NOT NULL DEFAULT 1,
    resume_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, store_id, attempt_id),
    FOREIGN KEY (tenant_id, store_id, batch_id)
        REFERENCES publication_batches (tenant_id, store_id, batch_id),
    FOREIGN KEY (tenant_id, store_id, item_id, version)
        REFERENCES knowledge_versions (tenant_id, store_id, item_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS publication_attempts_one_active_item
    ON publication_attempts (tenant_id, store_id, item_id)
    WHERE status IN ('in_progress', 'cleanup_pending');

CREATE TABLE IF NOT EXISTS publication_batch_items (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    attempt_id TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    PRIMARY KEY (tenant_id, store_id, batch_id, item_id),
    FOREIGN KEY (tenant_id, store_id, batch_id)
        REFERENCES publication_batches (tenant_id, store_id, batch_id)
);

CREATE TABLE IF NOT EXISTS published_knowledge_pointers (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    attempt_id TEXT NOT NULL,
    artifact_ref TEXT NOT NULL,
    published_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, item_id),
    FOREIGN KEY (tenant_id, store_id, item_id, version)
        REFERENCES knowledge_versions (tenant_id, store_id, item_id, version)
);

CREATE TABLE IF NOT EXISTS knowledge_publication_audit (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    attempt_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    safe_reason TEXT,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, event_id)
);

CREATE TABLE IF NOT EXISTS knowledge_retirement_cleanups (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    cleanup_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    artifact_ref TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'complete')),
    safe_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, store_id, cleanup_id),
    FOREIGN KEY (tenant_id, store_id, item_id, version)
        REFERENCES knowledge_versions (tenant_id, store_id, item_id, version)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope(scope: CommercialScope) -> tuple[str, str]:
    return str(scope.tenant_id), str(scope.store_id)


class SQLitePublicationStore:
    def __init__(self, path: str | Path):
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(resolved)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_draft(self, *, scope: CommercialScope, values: dict[str, Any], actor: str) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        item_id = f"ki_{uuid4().hex}"
        created_at = _now()
        checksum = hashlib.sha256(values["content"].encode("utf-8")).hexdigest()
        chunks = values.get("chunks") or [{"chunk_id": "c1", "content": values["content"]}]
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_items (
                    tenant_id, store_id, item_id, category, content_type,
                    row_revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (tenant_id, store_id, item_id, values["category"], values["content_type"], created_at, created_at),
            )
            conn.execute(
                """
                INSERT INTO knowledge_versions (
                    tenant_id, store_id, item_id, version, status, title,
                    content, content_checksum, chunks_json, created_at
                ) VALUES (?, ?, ?, 1, 'draft', ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    store_id,
                    item_id,
                    values["title"],
                    values["content"],
                    checksum,
                    json.dumps(chunks),
                    created_at,
                ),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=item_id,
                version=1,
                event_type="draft_created",
                actor=actor,
                occurred_at=created_at,
            )
        return self.get_item(scope=scope, item_id=item_id)

    def create_drafts(
        self, *, scope: CommercialScope, values: list[dict[str, Any]], actor: str
    ) -> list[dict[str, Any]]:
        tenant_id, store_id = _scope(scope)
        item_ids: list[str] = []
        with self._transaction() as conn:
            for row in values:
                item_id = f"ki_{uuid4().hex}"
                item_ids.append(item_id)
                created_at = _now()
                checksum = hashlib.sha256(row["content"].encode("utf-8")).hexdigest()
                chunks = row.get("chunks") or [{"chunk_id": "c1", "content": row["content"]}]
                conn.execute(
                    """
                    INSERT INTO knowledge_items (
                        tenant_id, store_id, item_id, category, content_type,
                        row_revision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        tenant_id,
                        store_id,
                        item_id,
                        row["category"],
                        row["content_type"],
                        created_at,
                        created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO knowledge_versions (
                        tenant_id, store_id, item_id, version, status, title,
                        content, content_checksum, chunks_json, created_at
                    ) VALUES (?, ?, ?, 1, 'draft', ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        store_id,
                        item_id,
                        row["title"],
                        row["content"],
                        checksum,
                        json.dumps(chunks),
                        created_at,
                    ),
                )
                self._audit(
                    conn,
                    tenant_id=tenant_id,
                    store_id=store_id,
                    item_id=item_id,
                    version=1,
                    event_type="draft_created",
                    actor=actor,
                    occurred_at=created_at,
                )
        return [self.get_item(scope=scope, item_id=item_id) for item_id in item_ids]

    def revise_draft(
        self,
        *,
        scope: CommercialScope,
        item_id: str,
        expected_row_revision: int,
        values: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        at = _now()
        checksum = hashlib.sha256(values["content"].encode("utf-8")).hexdigest()
        chunks = values.get("chunks") or [{"chunk_id": "c1", "content": values["content"]}]
        with self._transaction() as conn:
            item = conn.execute(
                """
                SELECT row_revision FROM knowledge_items
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (tenant_id, store_id, item_id),
            ).fetchone()
            if item is None:
                raise PublicationError("knowledge_item_not_found")
            if int(item["row_revision"]) != int(expected_row_revision):
                raise PublicationError(
                    "stale_knowledge_item",
                    details={"current_row_revision": int(item["row_revision"])},
                )
            version = (
                int(
                    conn.execute(
                        """
                    SELECT MAX(version) AS version FROM knowledge_versions
                    WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                    """,
                        (tenant_id, store_id, item_id),
                    ).fetchone()["version"]
                )
                + 1
            )
            conn.execute(
                """
                UPDATE knowledge_items
                SET category = ?, content_type = ?, row_revision = row_revision + 1, updated_at = ?
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (values["category"], values["content_type"], at, tenant_id, store_id, item_id),
            )
            conn.execute(
                """
                INSERT INTO knowledge_versions (
                    tenant_id, store_id, item_id, version, status, title,
                    content, content_checksum, chunks_json, created_at
                ) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    store_id,
                    item_id,
                    version,
                    values["title"],
                    values["content"],
                    checksum,
                    json.dumps(chunks),
                    at,
                ),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=item_id,
                version=version,
                event_type="draft_revised",
                actor=actor,
                occurred_at=at,
            )
        return self.get_item(scope=scope, item_id=item_id)

    def begin_batch(
        self,
        *,
        scope: CommercialScope,
        item_ids: list[str],
        actor: str,
        retry_failures_only: bool,
    ) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        batch_id = f"pb_{uuid4().hex}"
        created_at = _now()
        results: list[dict[str, Any]] = []
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO publication_batches (tenant_id, store_id, batch_id, actor, created_at) VALUES (?, ?, ?, ?, ?)",
                (tenant_id, store_id, batch_id, actor, created_at),
            )
            for item_id in item_ids:
                version = conn.execute(
                    """
                    SELECT version, status FROM knowledge_versions
                    WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                    ORDER BY version DESC LIMIT 1
                    """,
                    (tenant_id, store_id, item_id),
                ).fetchone()
                if version is None:
                    result = {
                        "item_id": item_id,
                        "status": "skipped",
                        "reason": "knowledge_item_not_found",
                    }
                    results.append(result)
                    conn.execute(
                        "INSERT INTO publication_batch_items VALUES (?, ?, ?, ?, NULL, ?, ?)",
                        (tenant_id, store_id, batch_id, item_id, result["status"], result["reason"]),
                    )
                    continue
                if version["status"] not in {"draft", "index_failed", "publication_failed"}:
                    result = {"item_id": item_id, "status": "skipped", "reason": "not_publishable"}
                    results.append(result)
                    conn.execute(
                        "INSERT INTO publication_batch_items VALUES (?, ?, ?, ?, NULL, ?, ?)",
                        (tenant_id, store_id, batch_id, item_id, result["status"], result["reason"]),
                    )
                    continue
                if retry_failures_only and version["status"] == "draft":
                    result = {"item_id": item_id, "status": "skipped", "reason": "not_failed"}
                    results.append(result)
                    conn.execute(
                        "INSERT INTO publication_batch_items VALUES (?, ?, ?, ?, NULL, ?, ?)",
                        (tenant_id, store_id, batch_id, item_id, result["status"], result["reason"]),
                    )
                    continue
                active = conn.execute(
                    """
                    SELECT attempt_id FROM publication_attempts
                    WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                      AND status IN ('in_progress', 'cleanup_pending')
                    """,
                    (tenant_id, store_id, item_id),
                ).fetchone()
                if active is not None:
                    result = {"item_id": item_id, "status": "skipped", "reason": "publication_in_progress"}
                    results.append(result)
                    conn.execute(
                        "INSERT INTO publication_batch_items VALUES (?, ?, ?, ?, NULL, ?, ?)",
                        (tenant_id, store_id, batch_id, item_id, result["status"], result["reason"]),
                    )
                    continue
                if version["status"] in {"index_failed", "publication_failed"}:
                    failed_attempt = conn.execute(
                        """
                        SELECT attempt_id FROM publication_attempts
                        WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                          AND version = ? AND status IN ('index_failed', 'publication_failed')
                        ORDER BY updated_at DESC LIMIT 1
                        """,
                        (tenant_id, store_id, item_id, version["version"]),
                    ).fetchone()
                    if failed_attempt is None:
                        raise PublicationError("failed_publication_attempt_not_found")
                    attempt_id = str(failed_attempt["attempt_id"])
                    conn.execute(
                        "INSERT INTO publication_batch_items VALUES (?, ?, ?, ?, ?, 'indexing', NULL)",
                        (tenant_id, store_id, batch_id, item_id, attempt_id),
                    )
                    results.append(
                        {
                            "item_id": item_id,
                            "version": int(version["version"]),
                            "attempt_id": attempt_id,
                            "status": "resuming",
                        }
                    )
                    continue
                attempt_id = f"pa_{uuid4().hex}"
                version_number = int(version["version"])
                conn.execute(
                    """
                    UPDATE knowledge_versions SET status = 'indexing'
                    WHERE tenant_id = ? AND store_id = ? AND item_id = ? AND version = ?
                    """,
                    (tenant_id, store_id, item_id, version_number),
                )
                conn.execute(
                    """
                    UPDATE knowledge_items SET row_revision = row_revision + 1, updated_at = ?
                    WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                    """,
                    (created_at, tenant_id, store_id, item_id),
                )
                conn.execute(
                    """
                    INSERT INTO publication_attempts (
                        tenant_id, store_id, attempt_id, batch_id, item_id,
                        version, phase, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'build', 'in_progress', ?, ?)
                    """,
                    (tenant_id, store_id, attempt_id, batch_id, item_id, version_number, created_at, created_at),
                )
                conn.execute(
                    "INSERT INTO publication_batch_items VALUES (?, ?, ?, ?, ?, 'indexing', NULL)",
                    (tenant_id, store_id, batch_id, item_id, attempt_id),
                )
                self._audit(
                    conn,
                    tenant_id=tenant_id,
                    store_id=store_id,
                    item_id=item_id,
                    version=version_number,
                    attempt_id=attempt_id,
                    event_type="indexing_started",
                    actor=actor,
                    occurred_at=created_at,
                )
                results.append(
                    {"item_id": item_id, "version": version_number, "attempt_id": attempt_id, "status": "indexing"}
                )
        return {"batch_id": batch_id, "results": results}

    def attach_job(self, *, scope: CommercialScope, attempt_id: str, job_id: str) -> None:
        tenant_id, store_id = _scope(scope)
        with self._transaction() as conn:
            updated = conn.execute(
                """
                UPDATE publication_attempts SET job_id = ?, updated_at = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ? AND status = 'in_progress'
                """,
                (job_id, _now(), tenant_id, store_id, attempt_id),
            ).rowcount
            if updated != 1:
                raise PublicationError("publication_attempt_not_found")

    def fail_enqueue(self, *, scope: CommercialScope, attempt_id: str, actor: str, reason: str) -> None:
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            attempt = conn.execute(
                """
                SELECT item_id, version FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (tenant_id, store_id, attempt_id),
            ).fetchone()
            if attempt is None:
                return
            conn.execute(
                """
                UPDATE publication_attempts
                SET status = 'index_failed', error_code = 'job_enqueue_failed',
                    safe_reason = ?, retry_eligible = 1, updated_at = ?, completed_at = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (reason, at, at, tenant_id, store_id, attempt_id),
            )
            conn.execute(
                """
                UPDATE knowledge_versions SET status = 'index_failed'
                WHERE tenant_id = ? AND store_id = ? AND item_id = ? AND version = ?
                """,
                (tenant_id, store_id, attempt["item_id"], attempt["version"]),
            )
            conn.execute(
                """
                UPDATE publication_batch_items
                SET status = 'index_failed', reason = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (reason, tenant_id, store_id, attempt_id),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=attempt["item_id"],
                version=int(attempt["version"]),
                attempt_id=attempt_id,
                event_type="job_enqueue_failed",
                actor=actor,
                safe_reason=reason,
                occurred_at=at,
            )

    def get_item(self, *, scope: CommercialScope, item_id: str) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            item = conn.execute(
                "SELECT * FROM knowledge_items WHERE tenant_id = ? AND store_id = ? AND item_id = ?",
                (tenant_id, store_id, item_id),
            ).fetchone()
            if item is None:
                raise PublicationError("knowledge_item_not_found", details={"item_id": item_id})
            versions = conn.execute(
                """
                SELECT * FROM knowledge_versions
                WHERE tenant_id = ? AND store_id = ? AND item_id = ? ORDER BY version
                """,
                (tenant_id, store_id, item_id),
            ).fetchall()
            pointer = conn.execute(
                """
                SELECT version FROM published_knowledge_pointers
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (tenant_id, store_id, item_id),
            ).fetchone()
        latest = versions[-1]
        return {
            "item_id": item_id,
            "category": item["category"],
            "content_type": item["content_type"],
            "row_revision": int(item["row_revision"]),
            "version": int(latest["version"]),
            "status": latest["status"],
            "published_version": int(pointer["version"]) if pointer is not None else None,
            "title": latest["title"],
            "content": latest["content"],
            "checksum": latest["content_checksum"],
            "chunks": json.loads(latest["chunks_json"]),
            "versions": [self._version_dict(row) for row in versions],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }

    def list_items(self, *, scope: CommercialScope) -> list[dict[str, Any]]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT item_id FROM knowledge_items
                WHERE tenant_id = ? AND store_id = ?
                ORDER BY updated_at DESC, item_id
                """,
                (tenant_id, store_id),
            ).fetchall()
        return [self.get_item(scope=scope, item_id=str(row["item_id"])) for row in rows]

    def get_batch(self, *, scope: CommercialScope, batch_id: str) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            batch = conn.execute(
                """
                SELECT actor, created_at FROM publication_batches
                WHERE tenant_id = ? AND store_id = ? AND batch_id = ?
                """,
                (tenant_id, store_id, batch_id),
            ).fetchone()
            if batch is None:
                raise PublicationError("publication_batch_not_found")
            rows = conn.execute(
                """
                SELECT item_id, attempt_id, status, reason
                FROM publication_batch_items
                WHERE tenant_id = ? AND store_id = ? AND batch_id = ?
                ORDER BY item_id
                """,
                (tenant_id, store_id, batch_id),
            ).fetchall()
        return {
            "batch_id": batch_id,
            "actor": batch["actor"],
            "created_at": batch["created_at"],
            "results": [
                {
                    "item_id": row["item_id"],
                    "attempt_id": row["attempt_id"],
                    "status": row["status"],
                    "reason": row["reason"],
                }
                for row in rows
            ],
        }

    def list_attempts(self, *, scope: CommercialScope, limit: int) -> list[dict[str, Any]]:
        tenant_id, store_id = _scope(scope)
        safe_limit = max(1, min(int(limit), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT attempt_id FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ?
                ORDER BY updated_at DESC, attempt_id
                LIMIT ?
                """,
                (tenant_id, store_id, safe_limit),
            ).fetchall()
        return [self.get_attempt(scope=scope, attempt_id=str(row["attempt_id"])) for row in rows]

    def list_audit(self, *, scope: CommercialScope, item_id: str) -> list[dict[str, Any]]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, version, attempt_id, event_type, actor,
                       safe_reason, occurred_at
                FROM knowledge_publication_audit
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                ORDER BY occurred_at, event_id
                """,
                (tenant_id, store_id, item_id),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "item_id": item_id,
                "version": int(row["version"]),
                "attempt_id": row["attempt_id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "safe_reason": row["safe_reason"],
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def get_attempt(self, *, scope: CommercialScope, attempt_id: str) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (tenant_id, store_id, attempt_id),
            ).fetchone()
        if row is None:
            raise PublicationError("publication_attempt_not_found")
        return {
            "tenant_id": tenant_id,
            "store_id": store_id,
            "attempt_id": row["attempt_id"],
            "batch_id": row["batch_id"],
            "item_id": row["item_id"],
            "version": int(row["version"]),
            "phase": row["phase"],
            "status": row["status"],
            "job_id": row["job_id"],
            "artifact_ref": row["artifact_ref"],
            "cleanup_artifact_ref": row["cleanup_artifact_ref"],
            "artifact_manifest": json.loads(row["artifact_manifest_json"]),
            "error_code": row["error_code"],
            "safe_reason": row["safe_reason"],
            "retry_eligible": bool(row["retry_eligible"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }

    def record_artifact(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        artifact: dict[str, Any],
    ) -> None:
        tenant_id, store_id = _scope(scope)
        artifact_ref = str(artifact.get("artifact_ref") or "").strip()
        if not artifact_ref:
            raise PublicationError("artifact_ref_required")
        with self._transaction() as conn:
            updated = conn.execute(
                """
                UPDATE publication_attempts
                SET phase = 'swap', artifact_ref = ?, artifact_manifest_json = ?, updated_at = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                  AND phase = 'build' AND status = 'in_progress'
                """,
                (artifact_ref, json.dumps(artifact, sort_keys=True), _now(), tenant_id, store_id, attempt_id),
            ).rowcount
            if updated != 1:
                raise PublicationError("publication_attempt_not_building")

    def list_expired_artifacts(self, *, cutoff: str, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT attempt_id, artifact_ref FROM publication_attempts
                WHERE status IN ('index_failed','publication_failed')
                  AND artifact_ref IS NOT NULL AND artifact_ref <> '' AND updated_at < ?
                ORDER BY updated_at LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
        return [{"attempt_id": str(row["attempt_id"]), "artifact_ref": str(row["artifact_ref"])} for row in rows]

    def clear_expired_artifact(self, *, attempt_id: str, actor: str) -> None:
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT tenant_id,store_id,item_id,version FROM publication_attempts WHERE attempt_id=? AND status IN ('index_failed','publication_failed')",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise PublicationError("publication_attempt_not_retained")
            conn.execute(
                "UPDATE publication_attempts SET artifact_ref=NULL,artifact_manifest_json='{}',updated_at=? WHERE attempt_id=?",
                (_now(), attempt_id),
            )
            self._audit(
                conn,
                tenant_id=row["tenant_id"],
                store_id=row["store_id"],
                item_id=row["item_id"],
                version=int(row["version"]),
                attempt_id=attempt_id,
                event_type="artifact_retention_cleanup",
                actor=actor,
                safe_reason="",
                occurred_at=_now(),
            )

    def commit_publication(self, *, scope: CommercialScope, attempt_id: str, actor: str) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            attempt = conn.execute(
                """
                SELECT * FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                  AND phase = 'swap' AND status = 'in_progress'
                """,
                (tenant_id, store_id, attempt_id),
            ).fetchone()
            if attempt is None:
                raise PublicationError("publication_attempt_not_swapping")
            previous = conn.execute(
                """
                SELECT version, artifact_ref FROM published_knowledge_pointers
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (tenant_id, store_id, attempt["item_id"]),
            ).fetchone()
            if previous is not None and int(previous["version"]) != int(attempt["version"]):
                conn.execute(
                    """
                    UPDATE knowledge_versions SET status = 'retired'
                    WHERE tenant_id = ? AND store_id = ? AND item_id = ? AND version = ?
                    """,
                    (tenant_id, store_id, attempt["item_id"], previous["version"]),
                )
            conn.execute(
                """
                UPDATE knowledge_versions SET status = 'published', published_at = ?
                WHERE tenant_id = ? AND store_id = ? AND item_id = ? AND version = ?
                """,
                (at, tenant_id, store_id, attempt["item_id"], attempt["version"]),
            )
            conn.execute(
                """
                INSERT INTO published_knowledge_pointers (
                    tenant_id, store_id, item_id, version, attempt_id, artifact_ref, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (tenant_id, store_id, item_id) DO UPDATE SET
                    version = excluded.version,
                    attempt_id = excluded.attempt_id,
                    artifact_ref = excluded.artifact_ref,
                    published_at = excluded.published_at
                """,
                (tenant_id, store_id, attempt["item_id"], attempt["version"], attempt_id, attempt["artifact_ref"], at),
            )
            cleanup_ref = previous["artifact_ref"] if previous is not None else None
            next_phase = "cleanup" if cleanup_ref else "complete"
            next_status = "cleanup_pending" if cleanup_ref else "published"
            completed_at = None if cleanup_ref else at
            conn.execute(
                """
                UPDATE publication_attempts
                SET phase = ?, status = ?, cleanup_artifact_ref = ?, updated_at = ?, completed_at = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (next_phase, next_status, cleanup_ref, at, completed_at, tenant_id, store_id, attempt_id),
            )
            conn.execute(
                """
                UPDATE publication_batch_items SET status = 'published', reason = NULL
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (tenant_id, store_id, attempt_id),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=attempt["item_id"],
                version=int(attempt["version"]),
                attempt_id=attempt_id,
                event_type="published",
                actor=actor,
                occurred_at=at,
            )
        return {"cleanup_artifact_ref": cleanup_ref}

    def complete_cleanup(self, *, scope: CommercialScope, attempt_id: str, actor: str) -> None:
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            attempt = conn.execute(
                """
                SELECT item_id, version FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                  AND phase = 'cleanup' AND status = 'cleanup_pending'
                """,
                (tenant_id, store_id, attempt_id),
            ).fetchone()
            if attempt is None:
                raise PublicationError("publication_attempt_not_cleaning")
            conn.execute(
                """
                UPDATE publication_attempts
                SET phase = 'complete', status = 'published', updated_at = ?, completed_at = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (at, at, tenant_id, store_id, attempt_id),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=attempt["item_id"],
                version=int(attempt["version"]),
                attempt_id=attempt_id,
                event_type="cleanup_completed",
                actor=actor,
                occurred_at=at,
            )

    def fail_swap(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
        reason: str,
    ) -> None:
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            attempt = conn.execute(
                """
                SELECT item_id, version FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                  AND phase = 'swap' AND status = 'in_progress'
                """,
                (tenant_id, store_id, attempt_id),
            ).fetchone()
            if attempt is None:
                return
            conn.execute(
                """
                UPDATE publication_attempts
                SET status = 'publication_failed', error_code = 'publication_swap_failed',
                    safe_reason = ?, retry_eligible = 1, updated_at = ?, completed_at = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (reason, at, at, tenant_id, store_id, attempt_id),
            )
            conn.execute(
                """
                UPDATE knowledge_versions SET status = 'publication_failed'
                WHERE tenant_id = ? AND store_id = ? AND item_id = ? AND version = ?
                """,
                (tenant_id, store_id, attempt["item_id"], attempt["version"]),
            )
            conn.execute(
                """
                UPDATE publication_batch_items SET status = 'publication_failed', reason = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (reason, tenant_id, store_id, attempt_id),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=attempt["item_id"],
                version=int(attempt["version"]),
                attempt_id=attempt_id,
                event_type="publication_failed",
                actor=actor,
                safe_reason=reason,
                occurred_at=at,
            )

    def record_retryable_error(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        error_code: str,
        reason: str,
    ) -> None:
        tenant_id, store_id = _scope(scope)
        with self._transaction() as conn:
            updated = conn.execute(
                """
                UPDATE publication_attempts
                SET error_code = ?, safe_reason = ?, retry_eligible = 1, updated_at = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                  AND status = 'in_progress'
                """,
                (error_code, reason, _now(), tenant_id, store_id, attempt_id),
            ).rowcount
            if updated != 1:
                raise PublicationError("publication_attempt_not_active")

    def fail_build(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
        error_code: str,
        reason: str,
    ) -> None:
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            attempt = conn.execute(
                """
                SELECT item_id, version FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                  AND phase = 'build' AND status = 'in_progress'
                """,
                (tenant_id, store_id, attempt_id),
            ).fetchone()
            if attempt is None:
                return
            conn.execute(
                """
                UPDATE publication_attempts
                SET status = 'index_failed', error_code = ?, safe_reason = ?,
                    retry_eligible = 1, updated_at = ?, completed_at = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (error_code, reason, at, at, tenant_id, store_id, attempt_id),
            )
            conn.execute(
                """
                UPDATE knowledge_versions SET status = 'index_failed'
                WHERE tenant_id = ? AND store_id = ? AND item_id = ? AND version = ?
                """,
                (tenant_id, store_id, attempt["item_id"], attempt["version"]),
            )
            conn.execute(
                """
                UPDATE publication_batch_items SET status = 'index_failed', reason = ?
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (reason, tenant_id, store_id, attempt_id),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=attempt["item_id"],
                version=int(attempt["version"]),
                attempt_id=attempt_id,
                event_type="index_failed",
                actor=actor,
                safe_reason=reason,
                occurred_at=at,
            )

    def resume_attempt(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
        reuse_artifact: bool,
    ) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            attempt = conn.execute(
                """
                SELECT item_id, version, status FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                  AND status IN ('index_failed', 'publication_failed')
                """,
                (tenant_id, store_id, attempt_id),
            ).fetchone()
            if attempt is None:
                raise PublicationError("publication_attempt_not_retryable")
            phase = "swap" if reuse_artifact else "build"
            artifact_sql = "" if reuse_artifact else ", artifact_ref = NULL, artifact_manifest_json = '{}'"
            conn.execute(
                f"""
                UPDATE publication_attempts
                SET phase = ?, status = 'in_progress', error_code = NULL,
                    safe_reason = NULL, completed_at = NULL, updated_at = ?,
                    resume_count = resume_count + 1{artifact_sql}
                WHERE tenant_id = ? AND store_id = ? AND attempt_id = ?
                """,
                (phase, at, tenant_id, store_id, attempt_id),
            )
            conn.execute(
                """
                UPDATE knowledge_versions SET status = 'indexing'
                WHERE tenant_id = ? AND store_id = ? AND item_id = ? AND version = ?
                """,
                (tenant_id, store_id, attempt["item_id"], attempt["version"]),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=attempt["item_id"],
                version=int(attempt["version"]),
                attempt_id=attempt_id,
                event_type="publication_resumed",
                actor=actor,
                occurred_at=at,
            )
        return self.get_attempt(scope=scope, attempt_id=attempt_id)

    def get_published(self, *, scope: CommercialScope, item_id: str) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM published_knowledge_pointers
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (tenant_id, store_id, item_id),
            ).fetchone()
        if row is None:
            raise PublicationError("published_knowledge_not_found")
        return {
            "item_id": row["item_id"],
            "version": int(row["version"]),
            "attempt_id": row["attempt_id"],
            "artifact_ref": row["artifact_ref"],
            "published_at": row["published_at"],
        }

    def list_published_attempt_ids(self, *, scope: CommercialScope) -> set[str]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT attempt_id FROM published_knowledge_pointers
                WHERE tenant_id = ? AND store_id = ?
                """,
                (tenant_id, store_id),
            ).fetchall()
        return {str(row["attempt_id"]) for row in rows}

    def begin_retirement(
        self,
        *,
        scope: CommercialScope,
        item_id: str,
        expected_row_revision: int,
        actor: str,
    ) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        cleanup_id = f"krc_{uuid4().hex}"
        at = _now()
        with self._transaction() as conn:
            item = conn.execute(
                """
                SELECT row_revision FROM knowledge_items
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (tenant_id, store_id, item_id),
            ).fetchone()
            if item is None:
                raise PublicationError("knowledge_item_not_found")
            if int(item["row_revision"]) != int(expected_row_revision):
                raise PublicationError(
                    "stale_knowledge_item",
                    details={"current_row_revision": int(item["row_revision"])},
                )
            active = conn.execute(
                """
                SELECT 1 FROM publication_attempts
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                  AND status IN ('in_progress', 'cleanup_pending')
                """,
                (tenant_id, store_id, item_id),
            ).fetchone()
            if active is not None:
                raise PublicationError("publication_in_progress")
            pointer = conn.execute(
                """
                SELECT version, artifact_ref FROM published_knowledge_pointers
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (tenant_id, store_id, item_id),
            ).fetchone()
            if pointer is None:
                raise PublicationError("published_knowledge_not_found")
            version = int(pointer["version"])
            conn.execute(
                """
                UPDATE knowledge_versions SET status = 'retired'
                WHERE tenant_id = ? AND store_id = ? AND item_id = ? AND version = ?
                """,
                (tenant_id, store_id, item_id, version),
            )
            conn.execute(
                """
                DELETE FROM published_knowledge_pointers
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (tenant_id, store_id, item_id),
            )
            conn.execute(
                """
                UPDATE knowledge_items
                SET row_revision = row_revision + 1, updated_at = ?
                WHERE tenant_id = ? AND store_id = ? AND item_id = ?
                """,
                (at, tenant_id, store_id, item_id),
            )
            conn.execute(
                """
                INSERT INTO knowledge_retirement_cleanups (
                    tenant_id, store_id, cleanup_id, item_id, version,
                    artifact_ref, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (tenant_id, store_id, cleanup_id, item_id, version, pointer["artifact_ref"], at, at),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=item_id,
                version=version,
                event_type="retired",
                actor=actor,
                occurred_at=at,
            )
        return self.get_retirement_cleanup(scope=scope, cleanup_id=cleanup_id)

    def purge_item(self, *, scope: CommercialScope, item_id: str) -> None:
        """刪除知識本體與其版本。

        順序必須由參照方往被參照方刪：publication_attempts 與 published_knowledge_pointers
        都指向 knowledge_versions，versions 又指向 items，先刪父列會直接違反外鍵。
        knowledge_publication_audit 沒有外鍵且刻意不刪，「誰在何時刪了什麼」才追溯得到。
        """

        tenant_id, store_id = _scope(scope)
        with self._transaction() as conn:
            for table in (
                "publication_batch_items",
                "publication_attempts",
                "published_knowledge_pointers",
                "knowledge_retirement_cleanups",
                "knowledge_versions",
                "knowledge_items",
            ):
                conn.execute(
                    f"DELETE FROM {table} WHERE tenant_id = ? AND store_id = ? AND item_id = ?",
                    (tenant_id, store_id, item_id),
                )

    def get_retirement_cleanup(self, *, scope: CommercialScope, cleanup_id: str) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM knowledge_retirement_cleanups
                WHERE tenant_id = ? AND store_id = ? AND cleanup_id = ?
                """,
                (tenant_id, store_id, cleanup_id),
            ).fetchone()
        if row is None:
            raise PublicationError("retirement_cleanup_not_found")
        return {
            "cleanup_id": row["cleanup_id"],
            "item_id": row["item_id"],
            "version": int(row["version"]),
            "artifact_ref": row["artifact_ref"],
            "status": row["status"],
            "safe_reason": row["safe_reason"],
        }

    def record_retirement_cleanup_error(self, *, scope: CommercialScope, cleanup_id: str, reason: str) -> None:
        tenant_id, store_id = _scope(scope)
        with self._transaction() as conn:
            updated = conn.execute(
                """
                UPDATE knowledge_retirement_cleanups
                SET safe_reason = ?, updated_at = ?
                WHERE tenant_id = ? AND store_id = ? AND cleanup_id = ? AND status = 'pending'
                """,
                (reason, _now(), tenant_id, store_id, cleanup_id),
            ).rowcount
            if updated != 1:
                raise PublicationError("retirement_cleanup_not_pending")

    def complete_retirement_cleanup(self, *, scope: CommercialScope, cleanup_id: str, actor: str) -> None:
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            row = conn.execute(
                """
                SELECT item_id, version FROM knowledge_retirement_cleanups
                WHERE tenant_id = ? AND store_id = ? AND cleanup_id = ? AND status = 'pending'
                """,
                (tenant_id, store_id, cleanup_id),
            ).fetchone()
            if row is None:
                raise PublicationError("retirement_cleanup_not_pending")
            conn.execute(
                """
                UPDATE knowledge_retirement_cleanups
                SET status = 'complete', safe_reason = NULL, updated_at = ?, completed_at = ?
                WHERE tenant_id = ? AND store_id = ? AND cleanup_id = ?
                """,
                (at, at, tenant_id, store_id, cleanup_id),
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                store_id=store_id,
                item_id=row["item_id"],
                version=int(row["version"]),
                event_type="retirement_cleanup_completed",
                actor=actor,
                occurred_at=at,
            )

    @staticmethod
    def _version_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "version": int(row["version"]),
            "status": row["status"],
            "title": row["title"],
            "content": row["content"],
            "checksum": row["content_checksum"],
            "chunks": json.loads(row["chunks_json"]),
            "created_at": row["created_at"],
            "published_at": row["published_at"],
        }

    @staticmethod
    def _audit(
        conn: sqlite3.Connection,
        *,
        tenant_id: str,
        store_id: str,
        item_id: str,
        version: int,
        event_type: str,
        actor: str,
        occurred_at: str,
        attempt_id: str | None = None,
        safe_reason: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO knowledge_publication_audit (
                tenant_id, store_id, event_id, item_id, version, attempt_id,
                event_type, actor, safe_reason, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                store_id,
                f"pae_{uuid4().hex}",
                item_id,
                version,
                attempt_id,
                event_type,
                actor,
                safe_reason,
                occurred_at,
            ),
        )
