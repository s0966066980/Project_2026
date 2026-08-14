"""Clearing recommendation events keeps the window the overview reads.

These rows are not only a log. The operations overview computes the push
funnel from the same events, so a clear that took everything would blank the
statistics an operator had just been reading. The default keeps thirty days.

On PostgreSQL because the cutoff is a SQL predicate, and the column it filters
on is `"timestamp"` — TEXT holding an ISO-8601 instant, not a `timestamptz`
called `created_at`. The first version of this filter named the wrong column
and would have raised on every call.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.recommendation.adapters import events as recommendation_events
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.contract]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="the cutoff is a SQL predicate over the PostgreSQL table",
    )
)

SCOPE = LEGACY_DEFAULT_SCOPE
DEVICE = uuid.UUID("00000000-0000-4000-8000-000000000003")
MARKER = "clear-gate"


def _insert(event_id: str, *, days_old: int) -> None:
    stamp = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO recommendation_events
                (event_id, tenant_id, store_id, device_id, session_id, event_type, "timestamp")
            VALUES (%s, %s, %s, %s, %s, 'impression', %s)
            """,
            (event_id, SCOPE.tenant_id, SCOPE.store_id, DEVICE, MARKER, stamp),
        )
        conn.commit()


def _surviving(*event_ids: str) -> set[str]:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT event_id FROM recommendation_events WHERE event_id = ANY(%s)",
            (list(event_ids),),
        )
        return {str(row["event_id"]) for row in cur.fetchall()}


def _purge(*event_ids: str) -> None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM recommendation_events WHERE event_id = ANY(%s)", (list(event_ids),))
        conn.commit()


def test_the_default_clear_keeps_the_last_thirty_days():
    recent = f"rec-recent-{uuid.uuid4().hex[:10]}"
    stale = f"rec-stale-{uuid.uuid4().hex[:10]}"

    _insert(recent, days_old=2)
    _insert(stale, days_old=90)
    try:
        recommendation_events.clear_recommendation_events_scoped(SCOPE)

        assert _surviving(recent, stale) == {recent}, (
            "the default clear either kept the old rows or took the window the overview reads"
        )
    finally:
        _purge(recent, stale)


def test_a_zero_cutoff_clears_everything_for_the_operator_who_asks():
    recent = f"rec-all-{uuid.uuid4().hex[:10]}"

    _insert(recent, days_old=1)
    try:
        recommendation_events.clear_recommendation_events_scoped(SCOPE, older_than_days=0)

        assert _surviving(recent) == set()
    finally:
        _purge(recent)


def test_the_clear_reports_how_many_rows_it_removed():
    """The Admin panel tells the operator what happened; it needs a number."""

    stale = [f"rec-count-{uuid.uuid4().hex[:10]}" for _ in range(3)]
    for event_id in stale:
        _insert(event_id, days_old=60)

    try:
        removed = recommendation_events.clear_recommendation_events_scoped(SCOPE, older_than_days=30)

        assert removed >= 3, f"reported {removed} for at least three stale rows"
        assert _surviving(*stale) == set()
    finally:
        _purge(*stale)


def test_another_store_keeps_its_events():
    mine = f"rec-mine-{uuid.uuid4().hex[:10]}"
    _insert(mine, days_old=90)

    other = uuid.uuid4()
    try:
        recommendation_events.clear_recommendation_events_scoped(type(SCOPE)(SCOPE.tenant_id, other), older_than_days=0)

        assert _surviving(mine) == {mine}, "clearing one store took another store's events"
    finally:
        _purge(mine)
