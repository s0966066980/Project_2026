from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


class SQLiteVoiceEvidenceStore:
    """Persistence adapter for the Voice Evidence capability.

    The adapter deliberately exposes separate metadata and bounded snapshot
    reads so HTTP consumers cannot accidentally receive conversation text.
    """

    def __init__(self, path: str | Path):
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(resolved)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS voice_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    voice_turn_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    terminal_status TEXT NOT NULL,
                    failure_type TEXT NOT NULL,
                    retry_outcome TEXT NOT NULL,
                    rag_outcome TEXT NOT NULL,
                    rag_refs_json TEXT NOT NULL,
                    transcript_masked TEXT NOT NULL,
                    assistant_text_masked TEXT NOT NULL,
                    has_transcript INTEGER NOT NULL,
                    has_assistant_text INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    projection_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    UNIQUE (tenant_id, store_id, voice_turn_id)
                );
                CREATE INDEX IF NOT EXISTS voice_evidence_scope_time
                    ON voice_evidence (tenant_id, store_id, observed_at DESC, evidence_id DESC);
                CREATE TABLE IF NOT EXISTS voice_evidence_outbox (
                    event_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    voice_turn_id TEXT NOT NULL,
                    terminal_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    available_at TEXT NOT NULL,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    projected_at TEXT,
                    UNIQUE (tenant_id, store_id, voice_turn_id)
                );
                CREATE INDEX IF NOT EXISTS voice_evidence_outbox_pending
                    ON voice_evidence_outbox (status, available_at, created_at);
                CREATE TABLE IF NOT EXISTS voice_evidence_backfill_runs (
                    run_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    enqueued INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create(self, *, scope, record: dict[str, Any]) -> dict[str, Any]:
        tenant_id, store_id = str(scope.tenant_id), str(scope.store_id)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM voice_evidence WHERE tenant_id=? AND store_id=? AND voice_turn_id=?",
                (tenant_id, store_id, record["voice_turn_id"]),
            ).fetchone()
            if existing is not None:
                return self._row(existing)
            connection.execute(
                """
                INSERT INTO voice_evidence (
                    evidence_id, tenant_id, store_id, voice_turn_id, observed_at,
                    terminal_status, failure_type, retry_outcome, rag_outcome,
                    rag_refs_json, transcript_masked, assistant_text_masked,
                    has_transcript, has_assistant_text, source, projection_status,
                    created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("evidence_id") or f"vie_{uuid4().hex}",
                    tenant_id,
                    store_id,
                    record["voice_turn_id"],
                    record["observed_at"],
                    record["terminal_status"],
                    record["failure_type"],
                    record["retry_outcome"],
                    record["rag_outcome"],
                    json.dumps(record.get("rag_refs") or {}, separators=(",", ":")),
                    record["transcript_masked"],
                    record["assistant_text_masked"],
                    # `bool`, not `int`. SQLite has no boolean type and stores
                    # these as 0/1 either way, but the PostgreSQL columns are
                    # `boolean` and refuse a smallint outright — the second
                    # half of why no Voice Turn ever became evidence.
                    bool(record["transcript_masked"]),
                    bool(record["assistant_text_masked"]),
                    record["source"],
                    record.get("projection_status", "projected"),
                    record["created_at"],
                    record["expires_at"],
                ),
            )
            row = connection.execute(
                "SELECT * FROM voice_evidence WHERE tenant_id=? AND store_id=? AND voice_turn_id=?",
                (tenant_id, store_id, record["voice_turn_id"]),
            ).fetchone()
        return self._row(row)

    def enqueue_terminal_turn(self, *, scope, terminal: dict[str, Any]) -> None:
        tenant_id, store_id = str(scope.tenant_id), str(scope.store_id)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO voice_evidence_outbox (
                    event_id, tenant_id, store_id, voice_turn_id, terminal_json,
                    status, attempts, available_at, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                ON CONFLICT (tenant_id, store_id, voice_turn_id) DO NOTHING
                """,
                (
                    # A bare UUID, not a prefixed one. `voice_evidence.evidence_id`
                    # is TEXT and takes `vie_…` happily, but this table's
                    # `event_id` is a PostgreSQL `uuid`, and a prefixed string
                    # made every enqueue fail with InvalidTextRepresentation —
                    # silently, because the caller treats evidence as
                    # non-blocking. SQLite's TEXT column accepts this form too.
                    str(uuid4()),
                    tenant_id,
                    store_id,
                    str(terminal["voice_turn_id"]),
                    json.dumps(terminal, ensure_ascii=False, separators=(",", ":")),
                    _now(),
                    _now(),
                ),
            )

    def begin_backfill(self, *, run_key: str) -> bool:
        """Claim the one-shot backfill, and let a crashed run be claimed again.

        `ON CONFLICT DO NOTHING` alone made a run that died mid-flight
        indistinguishable from one that finished: the row stayed `running`
        forever and every later start reported `already_completed` while
        nothing had been enqueued. That is exactly what happened here — the
        enqueue raised on a PostgreSQL type mismatch, the run key was left
        claimed, and the 25 turns already on disk could never be backfilled.

        Only a `completed` run blocks a retry now.
        """

        with self._transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO voice_evidence_backfill_runs (run_key,status,created_at)
                VALUES (?, 'running', ?)
                ON CONFLICT (run_key) DO UPDATE
                    SET status='running', created_at=excluded.created_at
                    WHERE voice_evidence_backfill_runs.status <> 'completed'
                """,
                (run_key, _now()),
            )
            return cursor.rowcount == 1

    def complete_backfill(self, *, run_key: str, enqueued: int) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE voice_evidence_backfill_runs SET status='completed', completed_at=?, enqueued=? WHERE run_key=?",
                (_now(), int(enqueued), run_key),
            )

    def claim_pending(self, *, limit: int = 50) -> list[dict[str, Any]]:
        claimed: list[dict[str, Any]] = []
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT * FROM voice_evidence_outbox
                WHERE status='pending' AND available_at<=?
                ORDER BY created_at, event_id
                LIMIT ?
                """,
                (_now(), max(1, min(int(limit), 100))),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE voice_evidence_outbox SET status='processing', attempts=attempts+1 WHERE event_id=?",
                    (row["event_id"],),
                )
                claimed.append(
                    {
                        "event_id": row["event_id"],
                        "tenant_id": row["tenant_id"],
                        "store_id": row["store_id"],
                        "terminal": json.loads(row["terminal_json"]),
                        "attempts": int(row["attempts"]) + 1,
                    }
                )
        return claimed

    def mark_projected(self, *, event_id: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE voice_evidence_outbox SET status='projected', projected_at=?, last_error='' WHERE event_id=?",
                (_now(), event_id),
            )

    def mark_failed(self, *, event_id: str, safe_error: str, retryable: bool = True) -> dict[str, Any]:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT attempts FROM voice_evidence_outbox WHERE event_id=?",
                (event_id,),
            ).fetchone()
            attempts = int(row["attempts"]) if row else 0
            status = "pending" if retryable and attempts < 5 else "failed"
            connection.execute(
                "UPDATE voice_evidence_outbox SET status=?, available_at=?, last_error=? WHERE event_id=?",
                (status, _now(), str(safe_error)[:200], event_id),
            )
        return {"status": status, "attempts": attempts}

    def reconciliation(self, *, scope, observed_from: str, observed_to: str) -> dict[str, int | str]:
        tenant_id, store_id = str(scope.tenant_id), str(scope.store_id)
        connection = self._connect()
        try:
            evidence_rows = connection.execute(
                "SELECT evidence_id FROM voice_evidence WHERE tenant_id=? AND store_id=? AND observed_at>=? AND observed_at<? AND expires_at>?",
                (tenant_id, store_id, observed_from, observed_to, _now()),
            ).fetchall()
            outbox_rows = connection.execute(
                "SELECT status,terminal_json FROM voice_evidence_outbox WHERE tenant_id=? AND store_id=? AND status IN ('pending','processing','failed')",
                (tenant_id, store_id),
            ).fetchall()
        finally:
            connection.close()
        unresolved = {"pending": 0, "processing": 0, "failed": 0}
        for row in outbox_rows:
            terminal = json.loads(row["terminal_json"])
            observed = str(terminal.get("observed_at") or "")
            if observed_from <= observed < observed_to:
                unresolved[str(row["status"])] += 1
        found = len(evidence_rows)
        awaiting = unresolved["pending"] + unresolved["processing"]
        permanent = unresolved["failed"]
        accepted = found + awaiting + permanent
        if accepted == 0:
            status = "true_zero"
        elif permanent and not awaiting:
            status = "permanent_projection_failure"
        elif awaiting:
            status = "awaiting_projection"
        else:
            status = "ready"
        return {
            "status": status,
            "backend_accepted": accepted,
            "found": found,
            "adopted": found,
            "excluded": 0,
            "awaiting_projection": awaiting,
            "permanent_projection_failure": permanent,
        }

    def list_metadata(
        self,
        *,
        scope,
        observed_from: str,
        observed_to: str,
        terminal_status: str | None = None,
        failure_type: str | None = None,
        rag_outcome: str | None = None,
        limit: int = 50,
        after: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        tenant_id, store_id = str(scope.tenant_id), str(scope.store_id)
        clauses = [
            "tenant_id=?",
            "store_id=?",
            "observed_at>=?",
            "observed_at<?",
            "expires_at>?",
        ]
        params: list[Any] = [tenant_id, store_id, observed_from, observed_to, _now()]
        for column, value in (
            ("terminal_status", terminal_status),
            ("failure_type", failure_type),
            ("rag_outcome", rag_outcome),
        ):
            if value:
                clauses.append(f"{column}=?")
                params.append(value)
        if after:
            clauses.append("(observed_at < ? OR (observed_at = ? AND evidence_id < ?))")
            params.extend([after[0], after[0], after[1]])
        params.append(max(1, min(int(limit), 100)))
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM voice_evidence WHERE {' AND '.join(clauses)} ORDER BY observed_at DESC, evidence_id DESC LIMIT ?",
                params,
            ).fetchall()
        finally:
            connection.close()
        return [self._metadata(row) for row in rows]

    def snapshot(
        self, *, scope, observed_from: str, observed_to: str, cutoff_at: str | None = None
    ) -> list[dict[str, Any]]:
        tenant_id, store_id = str(scope.tenant_id), str(scope.store_id)
        cutoff_clause = " AND observed_at<?" if cutoff_at else ""
        params: list[Any] = [tenant_id, store_id, observed_from, observed_to]
        if cutoff_at:
            params.append(cutoff_at)
        params.append(_now())
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT * FROM voice_evidence
                WHERE tenant_id=? AND store_id=? AND observed_at>=? AND observed_at<?{cutoff_clause} AND expires_at>?
                ORDER BY observed_at ASC, evidence_id ASC
                """,
                params,
            ).fetchall()
        finally:
            connection.close()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "evidence_id": row["evidence_id"],
            "voice_turn_id": row["voice_turn_id"],
            "observed_at": row["observed_at"],
            "terminal_status": row["terminal_status"],
            "failure_type": row["failure_type"],
            "retry_outcome": row["retry_outcome"],
            "rag_outcome": row["rag_outcome"],
            "rag_refs": json.loads(row["rag_refs_json"]),
            "transcript_masked": row["transcript_masked"],
            "assistant_text_masked": row["assistant_text_masked"],
            "has_transcript": bool(row["has_transcript"]),
            "has_assistant_text": bool(row["has_assistant_text"]),
            "source": row["source"],
            "projection_status": row["projection_status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    @classmethod
    def _metadata(cls, row: sqlite3.Row) -> dict[str, Any]:
        value = cls._row(row)
        for key in ("transcript_masked", "assistant_text_masked", "rag_refs"):
            value.pop(key, None)
        return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteVoiceEvidenceOutbox:
    """Durable enqueue/claim adapter used by Voice Turn and the worker."""

    def __init__(self, store: SQLiteVoiceEvidenceStore):
        self._store = store

    def enqueue_terminal_turn(self, **values: Any) -> None:
        self._store.enqueue_terminal_turn(**values)

    def claim_pending(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._store.claim_pending(limit=limit)

    def mark_projected(self, *, event_id: str) -> None:
        self._store.mark_projected(event_id=event_id)

    def mark_failed(self, *, event_id: str, safe_error: str, retryable: bool = True) -> dict[str, Any]:
        return self._store.mark_failed(event_id=event_id, safe_error=safe_error, retryable=retryable)

    def begin_backfill(self, *, run_key: str) -> bool:
        return self._store.begin_backfill(run_key=run_key)

    def complete_backfill(self, *, run_key: str, enqueued: int) -> None:
        self._store.complete_backfill(run_key=run_key, enqueued=enqueued)
