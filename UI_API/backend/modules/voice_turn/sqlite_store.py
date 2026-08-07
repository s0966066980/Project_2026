from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from models.commercial_scope import CommercialScope

from .module import VoiceTurnError

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS voice_turns (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    voice_turn_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'accepted', 'transcribing', 'assisting', 'synthesizing',
        'completed', 'transcription_failed', 'assistant_failed', 'playback_failed'
    )),
    audio_ref TEXT NOT NULL,
    transcript TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    assistant_text TEXT NOT NULL DEFAULT '',
    order_draft_json TEXT NOT NULL DEFAULT 'null',
    mentioned_ids_json TEXT NOT NULL DEFAULT '[]',
    tts_audio_ref TEXT NOT NULL DEFAULT '',
    tts_format TEXT NOT NULL DEFAULT '',
    playback_status TEXT NOT NULL DEFAULT '',
    safe_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, store_id, voice_turn_id)
);
CREATE TABLE IF NOT EXISTS voice_turn_events (
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    voice_turn_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    terminal INTEGER NOT NULL DEFAULT 0,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, voice_turn_id, sequence),
    FOREIGN KEY (tenant_id, store_id, voice_turn_id)
        REFERENCES voice_turns (tenant_id, store_id, voice_turn_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope(scope: CommercialScope) -> tuple[str, str]:
    return str(scope.tenant_id), str(scope.store_id)


class SQLiteVoiceTurnStore:
    def __init__(self, path: str | Path):
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(resolved)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self):
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

    def create(self, *, scope: CommercialScope, values: dict[str, Any]) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM voice_turns WHERE tenant_id=? AND store_id=? AND voice_turn_id=?",
                (tenant_id, store_id, values["voice_turn_id"]),
            ).fetchone()
            if existing is not None:
                if existing["session_id"] != values["session_id"]:
                    raise VoiceTurnError("voice_turn_identity_conflict")
                return self._row(existing)
            conn.execute(
                """
                INSERT INTO voice_turns (
                    tenant_id, store_id, voice_turn_id, session_id, status,
                    audio_ref, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'accepted', ?, ?, ?)
                """,
                (tenant_id, store_id, values["voice_turn_id"], values["session_id"], values["audio_ref"], at, at),
            )
            self._append_event(conn, tenant_id, store_id, values["voice_turn_id"], "accepted", {}, False, at)
        return self.get(scope=scope, voice_turn_id=values["voice_turn_id"])

    def get(self, *, scope: CommercialScope, voice_turn_id: str) -> dict[str, Any]:
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM voice_turns WHERE tenant_id=? AND store_id=? AND voice_turn_id=?",
                (tenant_id, store_id, voice_turn_id),
            ).fetchone()
        if row is None:
            raise VoiceTurnError("voice_turn_not_found")
        return self._row(row)

    def transition(self, *, scope, voice_turn_id, expected, status, updates, event_type, payload, terminal=False):
        tenant_id, store_id = _scope(scope)
        at = _now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT status FROM voice_turns WHERE tenant_id=? AND store_id=? AND voice_turn_id=?",
                (tenant_id, store_id, voice_turn_id),
            ).fetchone()
            if row is None:
                raise VoiceTurnError("voice_turn_not_found")
            if row["status"] not in expected:
                raise VoiceTurnError("invalid_voice_turn_transition", details={"current": row["status"]})
            columns = {**updates, "status": status, "updated_at": at}
            if terminal:
                columns["completed_at"] = at
            encoded = {
                key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                if key in {"order_draft", "mentioned_ids"}
                else value
                for key, value in columns.items()
            }
            db_names = {"order_draft": "order_draft_json", "mentioned_ids": "mentioned_ids_json"}
            assignments = ", ".join(f"{db_names.get(key, key)} = ?" for key in encoded)
            conn.execute(
                f"UPDATE voice_turns SET {assignments} WHERE tenant_id=? AND store_id=? AND voice_turn_id=?",
                (*encoded.values(), tenant_id, store_id, voice_turn_id),
            )
            self._append_event(conn, tenant_id, store_id, voice_turn_id, event_type, payload, terminal, at)
        return self.get(scope=scope, voice_turn_id=voice_turn_id)

    def record_error(self, *, scope, voice_turn_id, reason):
        tenant_id, store_id = _scope(scope)
        with self._transaction() as conn:
            conn.execute(
                "UPDATE voice_turns SET safe_reason=?, updated_at=? WHERE tenant_id=? AND store_id=? AND voice_turn_id=?",
                (reason, _now(), tenant_id, store_id, voice_turn_id),
            )

    def events(self, *, scope, voice_turn_id, after_sequence):
        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sequence, event_type, payload_json, terminal, occurred_at
                FROM voice_turn_events
                WHERE tenant_id=? AND store_id=? AND voice_turn_id=? AND sequence>?
                ORDER BY sequence
                """,
                (tenant_id, store_id, voice_turn_id, after_sequence),
            ).fetchall()
        return [
            {
                "voice_turn_id": voice_turn_id,
                "sequence": int(row["sequence"]),
                "type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "terminal": bool(row["terminal"]),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def cleanup_terminal_before(self, *, cutoff: str, limit: int) -> int:
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT tenant_id,store_id,voice_turn_id FROM voice_turns WHERE completed_at IS NOT NULL AND completed_at < ? ORDER BY completed_at LIMIT ?",
                (cutoff, limit),
            ).fetchall()
            keys = [(row["tenant_id"], row["store_id"], row["voice_turn_id"]) for row in rows]
            for key in keys:
                conn.execute("DELETE FROM voice_turn_events WHERE tenant_id=? AND store_id=? AND voice_turn_id=?", key)
                conn.execute("DELETE FROM voice_turns WHERE tenant_id=? AND store_id=? AND voice_turn_id=?", key)
        return len(keys)

    def count_completed_since(self, *, scope: CommercialScope, since: str) -> int:
        """Voice Turns whose speech was produced and delivered.

        This is what a store manager sees as voice success. It cannot mean the
        customer heard it — only the browser knows that, and this pilot confirms
        audible output through TTS service health instead (ADR-0025).
        """

        tenant_id, store_id = _scope(scope)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM voice_turns"
                " WHERE tenant_id=? AND store_id=? AND status='completed' AND completed_at >= ?",
                (tenant_id, store_id, since),
            ).fetchone()
        return int((row["total"] if row else 0) or 0)

    @staticmethod
    def _append_event(conn, tenant_id, store_id, voice_turn_id, event_type, payload, terminal, at):
        sequence = int(
            conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next FROM voice_turn_events WHERE tenant_id=? AND store_id=? AND voice_turn_id=?",
                (tenant_id, store_id, voice_turn_id),
            ).fetchone()["next"]
        )
        conn.execute(
            "INSERT INTO voice_turn_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                store_id,
                voice_turn_id,
                sequence,
                event_type,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                bool(terminal),
                at,
            ),
        )

    @staticmethod
    def _row(row) -> dict[str, Any]:
        return {
            "voice_turn_id": row["voice_turn_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "audio_ref": row["audio_ref"],
            "transcript": row["transcript"],
            "language": row["language"],
            "assistant_text": row["assistant_text"],
            "order_draft": json.loads(row["order_draft_json"]),
            "mentioned_ids": json.loads(row["mentioned_ids_json"]),
            "tts_audio_ref": row["tts_audio_ref"],
            "tts_format": row["tts_format"],
            "playback_status": row["playback_status"],
            "safe_reason": row["safe_reason"],
        }
