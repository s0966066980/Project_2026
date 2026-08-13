"""PostgreSQL evidence for the Kiosk intervention routes."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.recommendation.adapters.interactions import get_intervention_logs_scoped
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql"
        or not postgres_utils.use_postgres(),
        reason="recommendation intervention route evidence requires PostgreSQL",
    )
)


def test_kiosk_intervention_routes_persist_and_update_scoped_outcome():
    session_id = f"intervention-route-gate-{uuid.uuid4().hex}"
    intervention_id = None

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/barrier_state",
            json={
                "session_id": session_id,
                "speech_text": "不知道吃什麼，請推薦",
                "ui_context": {"page_id": "menu_page", "service_open": False},
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["barrier_result"]["barrier_state"] == "menu_hesitation"
        assert body["intervention"]["action"] != "none"
        intervention_id = body["intervention_log"]["intervention_id"]

        result_response = client.post(
            "/api/v1/intervention_result",
            json={
                "intervention_id": intervention_id,
                "outcome": "accepted",
                "completed": True,
            },
        )

    assert result_response.status_code == 200, result_response.text
    assert result_response.json()["status"] == "success"
    updated_result = result_response.json()["log"]["result"]
    assert updated_result["outcome"] == "accepted"
    assert updated_result["completed"] is True
    assert updated_result["scenario_id"] == "menu_hesitation"

    try:
        rows = get_intervention_logs_scoped(LEGACY_DEFAULT_SCOPE, session_id=session_id)
        assert len(rows) == 1
        assert rows[0]["intervention_id"] == intervention_id
        assert rows[0]["result"] == updated_result
        assert rows[0]["barrier_result"]["barrier_state"] == "menu_hesitation"
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM intervention_outcomes WHERE tenant_id = %s AND store_id = %s AND intervention_id = %s",
                (
                    str(LEGACY_DEFAULT_SCOPE.tenant_id),
                    str(LEGACY_DEFAULT_SCOPE.store_id),
                    intervention_id,
                ),
            )
            conn.commit()
