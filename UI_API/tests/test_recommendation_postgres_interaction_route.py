"""PostgreSQL evidence for the Kiosk interaction publication route."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.recommendation.adapters.interactions import get_interaction_events_scoped
from repositories import postgres_utils


pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql"
        or not postgres_utils.use_postgres(),
        reason="recommendation route evidence requires PostgreSQL",
    )
)


def test_kiosk_interaction_route_publishes_one_scoped_privacy_safe_event():
    session_id = f"route-gate-{uuid.uuid4().hex}"
    payload = {
        "session_id": session_id,
        "page_id": "recommendation",
        "event_type": "click",
        "button_id": "offer-1",
        "metadata": {"secret": "must-not-persist", "source": "route-gate"},
            "ui_context": {"service_open": True},
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/interaction_event", json=payload)

    assert response.status_code == 200, response.text
    saved = response.json()["event"]
    assert saved["session_id"] == session_id
    assert saved["event_type"] == "click"
    assert saved["event_id"]

    try:
        rows = get_interaction_events_scoped(LEGACY_DEFAULT_SCOPE, session_id=session_id)
        assert len(rows) == 1
        assert rows[0]["event_id"] == saved["event_id"]
        assert rows[0]["metadata"] == {"source": "route-gate"}
        assert rows[0]["ui_context"] == {
            "page_id": "recommendation",
            "service_open": True,
        }
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM interaction_events WHERE tenant_id = %s AND store_id = %s AND event_id = %s",
                (
                    str(LEGACY_DEFAULT_SCOPE.tenant_id),
                    str(LEGACY_DEFAULT_SCOPE.store_id),
                    saved["event_id"],
                ),
            )
            conn.commit()
