from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from models.commercial_scope import CommercialScope

TERMINAL_STATUSES = frozenset({"completed", "transcription_failed", "assistant_failed", "playback_failed"})
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)")
_LONG_NUMBER = re.compile(r"(?<!\d)\d{9,}(?!\d)")


class VoiceEvidenceStore(Protocol):
    def create(self, *, scope, record: dict[str, Any]) -> dict[str, Any]: ...

    def list_metadata(self, *, scope, observed_from: str, observed_to: str, **filters) -> list[dict[str, Any]]: ...

    def snapshot(
        self, *, scope, observed_from: str, observed_to: str, cutoff_at: str | None = None
    ) -> list[dict[str, Any]]: ...

    def reconciliation(self, *, scope, observed_from: str, observed_to: str) -> dict[str, Any]: ...


class VoiceEvidenceOutbox(Protocol):
    def claim_pending(self, *, limit: int = 50) -> list[dict[str, Any]]: ...

    def mark_projected(self, *, event_id: str) -> None: ...

    def mark_failed(self, *, event_id: str, safe_error: str, retryable: bool = True) -> dict[str, Any]: ...

    def begin_backfill(self, *, run_key: str) -> bool: ...

    def complete_backfill(self, *, run_key: str, enqueued: int) -> None: ...


class VoiceEvidenceModule:
    """Owns the bounded, de-identified evidence read model for voice turns."""

    def __init__(self, *, store: VoiceEvidenceStore, clock=None):
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def project_terminal_turn(self, *, scope, terminal: dict[str, Any]) -> dict[str, Any]:
        status = str(terminal.get("status") or "").strip().lower()
        if status not in TERMINAL_STATUSES:
            raise ValueError("voice_evidence_requires_terminal_turn")
        observed = _parse_datetime(terminal.get("observed_at"))
        transcript = _mask(_text(terminal.get("user_text")))
        assistant = _mask(_text(terminal.get("assistant_text")))
        failure_type = (
            ""
            if status == "completed"
            else (
                _text(terminal.get("safe_reason"), limit=80).lower()
                or {
                    "transcription_failed": "stt_failed",
                    "assistant_failed": "assistant_failed",
                    "playback_failed": "playback_failed",
                }[status]
            )
        )
        record = {
            "evidence_id": f"vie_{uuid4().hex}",
            "voice_turn_id": _text(terminal.get("voice_turn_id"), limit=120),
            "observed_at": observed.isoformat(),
            "terminal_status": status,
            "failure_type": failure_type,
            "retry_outcome": _text(terminal.get("retry_outcome"), limit=40).lower() or "none",
            "rag_outcome": _rag_outcome(terminal.get("rag_outcome")),
            "rag_refs": _safe_refs(terminal.get("rag_refs")),
            "transcript_masked": transcript,
            "assistant_text_masked": assistant,
            "source": "voice_turn_terminal",
            "projection_status": "projected",
            "created_at": self._clock().isoformat(),
            "expires_at": (observed + timedelta(days=30)).isoformat(),
        }
        return self._store.create(scope=scope, record=record)

    def list_metadata(self, *, scope, observed_from: str, observed_to: str, **filters) -> list[dict[str, Any]]:
        return self._store.list_metadata(
            scope=scope,
            observed_from=observed_from,
            observed_to=observed_to,
            **filters,
        )

    def snapshot(
        self, *, scope, observed_from: str, observed_to: str, cutoff_at: str | None = None
    ) -> list[dict[str, Any]]:
        return self._store.snapshot(
            scope=scope,
            observed_from=observed_from,
            observed_to=observed_to,
            cutoff_at=cutoff_at,
        )

    def reconciliation(self, *, scope, observed_from: str, observed_to: str) -> dict[str, Any]:
        return self._store.reconciliation(scope=scope, observed_from=observed_from, observed_to=observed_to)

    def process_pending(self, *, outbox: VoiceEvidenceOutbox, limit: int = 50) -> dict[str, int]:
        projected = retried = failed = 0
        for event in outbox.claim_pending(limit=limit):
            try:
                # `str()` first: SQLite hands back the text it stored, but
                # psycopg converts a `uuid` column into a `UUID` object, and
                # `UUID(UUID(...))` raises. Coercing covers both stores.
                scope = CommercialScope(
                    tenant_id=UUID(str(event["tenant_id"])),
                    store_id=UUID(str(event["store_id"])),
                )
                self.project_terminal_turn(scope=scope, terminal=event["terminal"])
                outbox.mark_projected(event_id=event["event_id"])
                projected += 1
            except Exception as exc:  # noqa: BLE001 - the outbox owns retry state
                result = outbox.mark_failed(event_id=event["event_id"], safe_error=str(exc))
                if result.get("status") == "failed":
                    failed += 1
                else:
                    retried += 1
        return {"projected": projected, "retried": retried, "failed": failed}

    def backfill_terminal_turns(
        self,
        *,
        outbox: VoiceEvidenceOutbox,
        turns: list[dict[str, Any]],
        run_key: str,
        limit: int = 500,
    ) -> dict[str, Any]:
        if not outbox.begin_backfill(run_key=run_key):
            return {"status": "already_completed", "enqueued": 0}
        enqueued = 0
        for turn in list(turns or [])[: max(0, min(int(limit), 500))]:
            scope = CommercialScope(tenant_id=UUID(str(turn["tenant_id"])), store_id=UUID(str(turn["store_id"])))
            outbox.enqueue_terminal_turn(scope=scope, terminal=turn["terminal"])
            enqueued += 1
        outbox.complete_backfill(run_key=run_key, enqueued=enqueued)
        return {"status": "completed", "enqueued": enqueued}


def _parse_datetime(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _text(value: Any, *, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def _mask(text: str) -> str:
    masked = _EMAIL.sub("<redacted-email>", text)
    masked = _PHONE.sub("<redacted-phone>", masked)
    return _LONG_NUMBER.sub("<redacted-number>", masked)


def _rag_outcome(value: Any) -> str:
    candidate = _text(value, limit=20).lower()
    return candidate if candidate in {"hit", "miss", "not_run"} else "not_run"


def _safe_refs(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: _text(value.get(key), limit=120)
        for key in ("knowledge_ref", "publication_ref", "index_ref")
        if _text(value.get(key), limit=120)
    }
