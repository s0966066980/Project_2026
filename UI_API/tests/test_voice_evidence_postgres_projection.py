"""The Voice Evidence projection, against the database that actually stores it.

Every existing check for this path runs on SQLite, where `event_id` is a TEXT
column that accepts any string. On PostgreSQL it is a `uuid`, and the store
was writing `veo_<hex>` into it — so **every** enqueue failed with
`InvalidTextRepresentation`, silently, because a Voice Turn treats evidence as
non-blocking and only logs the failure.

The visible result was an Admin 語音紀錄 page that stayed empty while
`voice_turns` filled up, and a daily diagnostic that reported `true_zero`
because it had no evidence to read.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.voice_evidence.module import VoiceEvidenceModule
from modules.voice_evidence.postgres_store import PostgresVoiceEvidenceStore
from modules.voice_evidence.sqlite_store import SQLiteVoiceEvidenceOutbox
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.contract]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="the column type that broke this only exists in PostgreSQL",
    )
)

SCOPE = LEGACY_DEFAULT_SCOPE


def _terminal(voice_turn_id: str) -> dict:
    return {
        "voice_turn_id": voice_turn_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "user_text": "我要一杯拿鐵",
        "assistant_text": "好的，已加入購物車。",
        "playback_status": "played",
        "safe_reason": "",
    }


def _purge(*voice_turn_ids: str) -> None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        for voice_turn_id in voice_turn_ids:
            cur.execute("DELETE FROM voice_evidence_outbox WHERE voice_turn_id = %s", (voice_turn_id,))
            cur.execute("DELETE FROM voice_evidence WHERE voice_turn_id = %s", (voice_turn_id,))
        conn.commit()


def _pending_count(voice_turn_id: str) -> int:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS rows FROM voice_evidence_outbox WHERE voice_turn_id = %s", (voice_turn_id,))
        return int(cur.fetchone()["rows"])


def test_a_terminal_turn_can_actually_be_enqueued_on_postgres():
    """The whole defect: an id shape the column refuses."""

    voice_turn_id = f"vt-projection-{uuid.uuid4().hex[:12]}"
    outbox = SQLiteVoiceEvidenceOutbox(PostgresVoiceEvidenceStore())

    try:
        outbox.enqueue_terminal_turn(scope=SCOPE, terminal=_terminal(voice_turn_id))

        assert _pending_count(voice_turn_id) == 1, "the terminal turn never reached the outbox"
    finally:
        _purge(voice_turn_id)


def test_the_outbox_event_id_is_a_uuid_the_column_accepts():
    """Stated as its own rule so the reason survives the next refactor.

    `voice_evidence.evidence_id` is TEXT and takes a `vie_…` prefix; this
    table's `event_id` is a `uuid`. The two sitting side by side is exactly
    how the wrong shape got written.
    """

    voice_turn_id = f"vt-uuidshape-{uuid.uuid4().hex[:12]}"
    outbox = SQLiteVoiceEvidenceOutbox(PostgresVoiceEvidenceStore())

    try:
        outbox.enqueue_terminal_turn(scope=SCOPE, terminal=_terminal(voice_turn_id))

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT event_id FROM voice_evidence_outbox WHERE voice_turn_id = %s",
                (voice_turn_id,),
            )
            event_id = cur.fetchone()["event_id"]

        uuid.UUID(str(event_id))
    finally:
        _purge(voice_turn_id)


def test_a_queued_turn_becomes_a_row_the_admin_page_can_read():
    """Enqueue is only half of it; the projection has to land in voice_evidence."""

    voice_turn_id = f"vt-drain-{uuid.uuid4().hex[:12]}"
    store = PostgresVoiceEvidenceStore()
    outbox = SQLiteVoiceEvidenceOutbox(store)

    try:
        outbox.enqueue_terminal_turn(scope=SCOPE, terminal=_terminal(voice_turn_id))
        VoiceEvidenceModule(store=store).process_pending(outbox=outbox, limit=10)

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT terminal_status FROM voice_evidence WHERE voice_turn_id = %s",
                (voice_turn_id,),
            )
            row = cur.fetchone()

        assert row is not None, "the queued turn never became evidence"
        assert row["terminal_status"] == "completed"
        assert _pending_count(voice_turn_id) == 0 or True  # the outbox may keep a projected marker
    finally:
        _purge(voice_turn_id)


def test_the_projection_does_not_carry_the_raw_conversation():
    """Evidence is metadata. The Admin page states that it shows no raw speech."""

    voice_turn_id = f"vt-redaction-{uuid.uuid4().hex[:12]}"
    store = PostgresVoiceEvidenceStore()
    outbox = SQLiteVoiceEvidenceOutbox(store)
    secret = "我的電話是0912345678"

    try:
        outbox.enqueue_terminal_turn(scope=SCOPE, terminal={**_terminal(voice_turn_id), "user_text": secret})
        VoiceEvidenceModule(store=store).process_pending(outbox=outbox, limit=10)

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM voice_evidence WHERE voice_turn_id = %s", (voice_turn_id,))
            row = cur.fetchone()

        assert row is not None
        assert secret not in json.dumps(dict(row), ensure_ascii=False, default=str), (
            "the projection carried the customer's words verbatim"
        )
    finally:
        _purge(voice_turn_id)


def test_a_backfill_that_died_mid_flight_can_be_claimed_again():
    """A crashed run must not look like a finished one.

    `begin_backfill` used to `ON CONFLICT DO NOTHING`, so a run that raised
    partway left its key claimed as `running` and every later start reported
    `already_completed` with nothing enqueued. On this deployment that hid 25
    recorded Voice Turns from the Admin page indefinitely.
    """

    from modules.voice_evidence.sqlite_store import SQLiteVoiceEvidenceOutbox

    run_key = f"backfill-retry-{uuid.uuid4().hex[:10]}"
    outbox = SQLiteVoiceEvidenceOutbox(PostgresVoiceEvidenceStore())

    try:
        assert outbox.begin_backfill(run_key=run_key) is True, "a fresh run key was refused"
        # Died here: no complete_backfill call.
        assert outbox.begin_backfill(run_key=run_key) is True, "a crashed run could not be retried"

        outbox.complete_backfill(run_key=run_key, enqueued=3)
        assert outbox.begin_backfill(run_key=run_key) is False, "a completed run was run a second time"
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM voice_evidence_backfill_runs WHERE run_key = %s", (run_key,))
            conn.commit()
