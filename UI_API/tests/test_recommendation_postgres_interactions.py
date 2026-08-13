"""PostgreSQL evidence for the Recommendation interaction storage path."""

import os
import uuid

import pytest

from models.commercial_scope import CommercialScope
from modules.recommendation.adapters.interactions import (
    append_interaction_event_scoped,
    get_interaction_events_scoped,
)
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="recommendation interaction evidence requires PostgreSQL",
    )
)

SCOPE = CommercialScope(
    uuid.UUID("00000000-0000-4000-8000-000000000001"),
    uuid.UUID("00000000-0000-4000-8000-000000000002"),
    uuid.UUID("00000000-0000-4000-8000-000000000003"),
)


def test_postgres_interactions_are_scoped_and_event_id_is_idempotent():
    event_id = f"recommendation-interaction-gate-{uuid.uuid4().hex}"
    session_id = f"recommendation-session-{uuid.uuid4().hex}"
    try:
        first = append_interaction_event_scoped(
            {
                "event_id": event_id,
                "session_id": session_id,
                "event_type": "impression",
                "item_id": "tea",
                "metadata": {"source": "recommendation", "secret": "must-not-leak"},
            },
            SCOPE,
        )
        second = append_interaction_event_scoped(
            {
                "event_id": event_id,
                "session_id": session_id,
                "event_type": "click",
                "item_id": "tea",
                "metadata": {"source": "recommendation", "secret": "must-not-leak"},
            },
            SCOPE,
        )

        rows = get_interaction_events_scoped(SCOPE, session_id=session_id)

        assert first["event_id"] == event_id
        assert second["event_id"] == event_id
        assert len([row for row in rows if row["event_id"] == event_id]) == 1
        stored = next(row for row in rows if row["event_id"] == event_id)
        assert stored["event_type"] == "click"
        assert stored["session_id"] == session_id
        assert "secret" not in stored.get("metadata", {})
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM interaction_events "
                "WHERE tenant_id = %s AND store_id = %s AND device_id = %s AND event_id = %s",
                (SCOPE.tenant_id, SCOPE.store_id, SCOPE.device_id, event_id),
            )
            conn.commit()
