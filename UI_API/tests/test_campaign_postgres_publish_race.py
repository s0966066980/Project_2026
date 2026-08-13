"""PostgreSQL evidence for the campaign publish optimistic-concurrency boundary."""

from concurrent.futures import ThreadPoolExecutor
import os
import threading
import uuid

import pytest

from models.commercial_scope import CommercialScope
from modules.promotion.application import create_campaign_draft, publish_campaign
from modules.promotion.contracts import CampaignConflictError
from repositories import postgres_utils
from repositories.campaign_repository import CampaignRepository


pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql"
        or not postgres_utils.use_postgres(),
        reason="campaign publish race evidence requires PostgreSQL",
    )
)

TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")
SCOPE = CommercialScope(TENANT, STORE)


def _payload() -> dict:
    return {
        "name": f"publish-race-{uuid.uuid4().hex[:10]}",
        "objective": "promote_item",
        "audience": "all",
        "schedule": {"starts_at": "2099-08-14T00:00:00+08:00"},
        "placements": ["menu_card"],
        "promotion_rules": [
            {
                "type": "fixed_item_price",
                "item_ids": [f"item-{uuid.uuid4().hex[:8]}"],
                "promotion_price": 50,
            }
        ],
        "store_ids": [str(STORE)],
    }


class _OuterReadBarrierRepository(CampaignRepository):
    """Make both publishers observe the same draft before either appends."""

    def __init__(self):
        self._barrier = threading.Barrier(2)
        self._lock = threading.Lock()
        self._outer_reads = 0

    def get(self, scope, campaign_id):
        snapshot = super().get(scope, campaign_id)
        with self._lock:
            should_wait = self._outer_reads < 2
            if should_wait:
                self._outer_reads += 1
        if should_wait:
            self._barrier.wait(timeout=10)
        return snapshot


def _purge(campaign_id: str) -> None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM promotion_records WHERE tenant_id = %s AND store_id = %s AND promotion_id = %s",
            (str(TENANT), str(STORE), campaign_id),
        )
        cur.execute(
            "DELETE FROM admin_audit_logs WHERE target_type = 'campaign' AND target_id = %s",
            (campaign_id,),
        )
        cur.execute(
            "DELETE FROM campaign_definitions WHERE tenant_id = %s AND store_id = %s AND campaign_id = %s",
            (str(TENANT), str(STORE), campaign_id),
        )
        conn.commit()


def test_concurrent_publishers_share_one_winner_and_leave_one_durable_version():
    payload = _payload()
    created = create_campaign_draft(payload, SCOPE, actor_id="publish-race-setup")
    repository = _OuterReadBarrierRepository()

    def publish(actor_id: str):
        try:
            return publish_campaign(
                payload,
                SCOPE,
                campaign_id=created.campaign_id,
                expected_version=created.version,
                actor_id=actor_id,
                repository=repository,
            )
        except Exception as exc:  # preserve both concurrent outcomes for assertions
            return exc

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(publish, ("publisher-one", "publisher-two")))

        winners = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
        conflicts = [outcome for outcome in outcomes if isinstance(outcome, CampaignConflictError)]
        assert len(winners) == 1, outcomes
        assert len(conflicts) == 1, outcomes
        assert repository.get(SCOPE, created.campaign_id).version == winners[0].version
    finally:
        _purge(created.campaign_id)
