from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.models.commercial_scope import CommercialScope
from backend.modules.voice_evidence.module import VoiceEvidenceModule
from backend.modules.voice_evidence.sqlite_store import (
    SQLiteVoiceEvidenceOutbox,
    SQLiteVoiceEvidenceStore,
)
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.voice_turn.module import VoiceTurnModule
from modules.voice_turn.sqlite_store import SQLiteVoiceTurnStore

pytestmark = [pytest.mark.integration]


def _scope() -> CommercialScope:
    return CommercialScope(tenant_id=uuid4(), store_id=uuid4())


def test_terminal_voice_turn_is_projected_as_deidentified_metadata_and_is_idempotent(tmp_path):
    scope = _scope()
    module = VoiceEvidenceModule(store=SQLiteVoiceEvidenceStore(tmp_path / "evidence.db"))
    terminal = {
        "voice_turn_id": "turn-completed-1",
        "observed_at": "2026-08-14T09:30:00+08:00",
        "status": "completed",
        "user_text": "請寄到 0912345678，email oliver@example.com",
        "assistant_text": "好的，我已記下來",
        "playback_status": "available",
        "safe_reason": "",
    }

    first = module.project_terminal_turn(scope=scope, terminal=terminal)
    replay = module.project_terminal_turn(scope=scope, terminal=terminal)

    assert first["evidence_id"] == replay["evidence_id"]
    assert first["projection_status"] == "projected"

    metadata = module.list_metadata(
        scope=scope,
        observed_from="2026-08-14T00:00:00+08:00",
        observed_to="2026-08-15T00:00:00+08:00",
    )
    assert len(metadata) == 1
    assert metadata[0]["terminal_status"] == "completed"
    assert metadata[0]["has_transcript"] is True
    assert metadata[0]["has_assistant_text"] is True
    assert "user_text" not in metadata[0]
    assert "assistant_text" not in metadata[0]

    snapshot = module.snapshot(
        scope=scope,
        observed_from="2026-08-14T00:00:00+08:00",
        observed_to="2026-08-15T00:00:00+08:00",
    )
    assert len(snapshot) == 1
    assert "0912345678" not in snapshot[0]["transcript_masked"]
    assert "oliver@example.com" not in snapshot[0]["transcript_masked"]


def test_terminal_voice_turn_failure_is_still_evidence(tmp_path):
    scope = _scope()
    module = VoiceEvidenceModule(store=SQLiteVoiceEvidenceStore(tmp_path / "evidence.db"))

    projected = module.project_terminal_turn(
        scope=scope,
        terminal={
            "voice_turn_id": "turn-stt-failed-1",
            "observed_at": datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc).isoformat(),
            "status": "transcription_failed",
            "safe_reason": "stt_unavailable",
        },
    )

    assert projected["terminal_status"] == "transcription_failed"
    assert projected["failure_type"] == "stt_unavailable"
    assert (
        module.list_metadata(
            scope=scope,
            observed_from="2026-08-14T00:00:00+00:00",
            observed_to="2026-08-15T00:00:00+00:00",
        )[0]["has_transcript"]
        is False
    )


class _STT:
    def transcribe(self, **_kwargs):
        return {"text": "我要一份漢堡"}


class _Assistant:
    def assist(self, **_kwargs):
        return {"text": "好的，請在畫面確認。", "order_draft": None, "mentioned_ids": []}


class _Menu:
    def candidates(self, **_kwargs):
        return [{"item_id": "burger", "available": True}]


class _TTS:
    def synthesize(self, **_kwargs):
        return {"audio_ref": "d2F2", "format": "wav"}


class _Effects:
    def schedule_observation(self, **_kwargs):
        return None

    def record_history(self, **_kwargs):
        return None


class _TerminalEvidenceOutbox:
    def __init__(self):
        self.events = []

    def enqueue_terminal_turn(self, **values):
        self.events.append(values)


def test_voice_turn_enqueues_every_terminal_result_for_async_evidence_projection(tmp_path):
    outbox = _TerminalEvidenceOutbox()
    module = VoiceTurnModule(
        store=SQLiteVoiceTurnStore(tmp_path / "voice-turn.sqlite3"),
        stt=_STT(),
        assistant=_Assistant(),
        menu=_Menu(),
        tts=_TTS(),
        effects=_Effects(),
        terminal_evidence_outbox=outbox,
    )
    module.accept(
        scope=LEGACY_DEFAULT_SCOPE,
        session_id="session-1",
        audio_ref="/tmp/input.webm",
        voice_turn_id="turn-1",
    )

    result = module.run(scope=LEGACY_DEFAULT_SCOPE, voice_turn_id="turn-1")

    assert result["status"] == "completed"
    assert len(outbox.events) == 1
    assert outbox.events[0]["terminal"]["status"] == "completed"
    assert outbox.events[0]["terminal"]["user_text"] == "我要一份漢堡"
    assert outbox.events[0]["terminal"]["observed_at"]


def test_durable_evidence_outbox_projects_and_retries_without_duplicate_rows(tmp_path):
    scope = _scope()
    store = SQLiteVoiceEvidenceStore(tmp_path / "evidence.db")
    outbox = SQLiteVoiceEvidenceOutbox(store)
    module = VoiceEvidenceModule(store=store)
    terminal = {
        "voice_turn_id": "turn-outbox-1",
        "observed_at": "2026-08-14T09:30:00+08:00",
        "status": "completed",
        "user_text": "今天的訂單",
        "assistant_text": "已完成",
    }

    outbox.enqueue_terminal_turn(scope=scope, terminal=terminal)
    first = module.process_pending(outbox=outbox)
    replay = module.process_pending(outbox=outbox)

    assert first == {"projected": 1, "retried": 0, "failed": 0}
    assert replay == {"projected": 0, "retried": 0, "failed": 0}
    assert (
        len(
            module.list_metadata(
                scope=scope,
                observed_from="2026-08-14T00:00:00+08:00",
                observed_to="2026-08-15T00:00:00+08:00",
            )
        )
        == 1
    )


def test_reconciliation_distinguishes_awaiting_projection_from_true_zero(tmp_path):
    scope = _scope()
    store = SQLiteVoiceEvidenceStore(tmp_path / "evidence.db")
    outbox = SQLiteVoiceEvidenceOutbox(store)
    module = VoiceEvidenceModule(store=store)
    terminal = {
        "voice_turn_id": "turn-awaiting-1",
        "observed_at": "2026-08-14T09:30:00+08:00",
        "status": "completed",
    }

    zero = module.reconciliation(
        scope=scope,
        observed_from="2026-08-14T00:00:00+08:00",
        observed_to="2026-08-15T00:00:00+08:00",
    )
    outbox.enqueue_terminal_turn(scope=scope, terminal=terminal)
    awaiting = module.reconciliation(
        scope=scope,
        observed_from="2026-08-14T00:00:00+08:00",
        observed_to="2026-08-15T00:00:00+08:00",
    )
    module.process_pending(outbox=outbox)
    found = module.reconciliation(
        scope=scope,
        observed_from="2026-08-14T00:00:00+08:00",
        observed_to="2026-08-15T00:00:00+08:00",
    )

    assert zero["status"] == "true_zero"
    assert awaiting["status"] == "awaiting_projection"
    assert awaiting["awaiting_projection"] == 1
    assert found["adopted"] == 1
    assert found["status"] == "ready"


def test_bounded_backfill_is_idempotent_and_does_not_exceed_its_limit(tmp_path):
    scope = _scope()
    store = SQLiteVoiceEvidenceStore(tmp_path / "evidence.db")
    outbox = SQLiteVoiceEvidenceOutbox(store)
    module = VoiceEvidenceModule(store=store)
    turns = [
        {
            "tenant_id": str(scope.tenant_id),
            "store_id": str(scope.store_id),
            "terminal": {
                "voice_turn_id": f"legacy-turn-{index}",
                "observed_at": "2026-08-14T09:30:00+08:00",
                "status": "completed",
            },
        }
        for index in range(2)
    ]

    first = module.backfill_terminal_turns(outbox=outbox, turns=turns, run_key="voice-turns-v1", limit=1)
    second = module.backfill_terminal_turns(outbox=outbox, turns=turns, run_key="voice-turns-v1", limit=2)

    assert first == {"status": "completed", "enqueued": 1}
    assert second == {"status": "already_completed", "enqueued": 0}
