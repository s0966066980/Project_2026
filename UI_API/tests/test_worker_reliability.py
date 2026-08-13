"""Evidence for durable job and order outbox worker guarantees."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from models.worker_jobs import JobHandlerResult, OutboxDeliveryResult
from modules.operations._worker import (
    InMemoryJobStore,
    SimulatedWorkerCrash,
    deliver_one_outbox,
    deliver_outbox_by_id,
    enqueue_job,
    process_one_job,
    set_outbox_delivery_handler,
)

pytestmark = pytest.mark.unit


def _ids():
    return uuid4(), uuid4()


def test_failed_job_retries_with_backoff_then_enters_dead_letter():
    store = InMemoryJobStore()
    tenant_id, store_id = _ids()
    now = datetime(2026, 8, 13, 4, 0, tzinfo=timezone.utc)
    job = enqueue_job(
        tenant_id=tenant_id,
        store_id=store_id,
        job_type="cleanup.retention",
        payload_ref={"retention_scope": "store"},
        idempotency_key="retention-1",
        max_attempts=2,
        store=store,
        scheduled_at=now,
    )

    def failure(_job):
        return JobHandlerResult(success=False, retryable=True, safe_error="temporary")

    first = process_one_job(store=store, now=now, handler=failure)
    assert first is not None
    assert first.status.value == "pending"
    assert first.attempt_count == 1
    assert first.available_at == now + timedelta(seconds=2)

    second = process_one_job(store=store, now=now + timedelta(seconds=2), handler=failure)
    assert second is not None
    assert second.status.value == "dead_letter"
    assert second.finished_at == now + timedelta(seconds=2)
    assert store.metrics(now=now + timedelta(seconds=2)).dead_letter_count == 1
    assert store.get_job(job.job_id).status.value == "dead_letter"


def test_worker_crash_leaves_job_reclaimable_after_visibility_timeout():
    store = InMemoryJobStore()
    tenant_id, store_id = _ids()
    now = datetime(2026, 8, 13, 4, 0, tzinfo=timezone.utc)
    job = enqueue_job(
        tenant_id=tenant_id,
        store_id=store_id,
        job_type="event.deliver",
        payload_ref={"event_id": "event-1"},
        idempotency_key="event-1",
        visibility_timeout_seconds=3,
        store=store,
        scheduled_at=now,
    )

    with pytest.raises(SimulatedWorkerCrash):
        process_one_job(
            store=store,
            now=now,
            handler=lambda _job: (_ for _ in ()).throw(SimulatedWorkerCrash()),
        )

    running = store.get_job(job.job_id)
    assert running is not None
    assert running.status.value == "running"
    assert running.attempt_count == 1

    recovered = process_one_job(
        store=store,
        now=now + timedelta(seconds=3),
        handler=lambda _job: JobHandlerResult(success=True, side_effect_id="delivery-1"),
    )
    assert recovered is not None
    assert recovered.status.value == "succeeded"
    assert recovered.attempt_count == 2


def test_outbox_retry_and_dead_letter_keep_event_available_only_until_budget_exhausted():
    store = InMemoryJobStore()
    tenant_id, store_id = _ids()
    event_id = uuid4()
    aggregate_id = uuid4()
    now = datetime(2026, 8, 13, 4, 0, tzinfo=timezone.utc)
    store.seed_outbox(
        outbox_id=event_id,
        tenant_id=tenant_id,
        store_id=store_id,
        aggregate_id=aggregate_id,
        event_type="order_confirmed",
        payload={"order_id": str(aggregate_id)},
        max_attempts=2,
        available_at=now,
    )
    set_outbox_delivery_handler(
        lambda _event: OutboxDeliveryResult(success=False, retryable=True, safe_error="offline")
    )
    try:
        first = deliver_one_outbox(store=store, now=now)
        assert first is not None
        assert first["dead_lettered_at"] is None
        assert first["available_at"] == now + timedelta(seconds=2)

        second = deliver_one_outbox(store=store, now=now + timedelta(seconds=2))
        assert second is not None
        assert second["dead_lettered_at"] == now + timedelta(seconds=2)
        assert deliver_one_outbox(store=store, now=now + timedelta(seconds=3)) is None
    finally:
        set_outbox_delivery_handler(None)


def test_published_outbox_is_idempotent_and_does_not_repeat_side_effect():
    store = InMemoryJobStore()
    tenant_id, store_id = _ids()
    event_id = uuid4()
    store.seed_outbox(
        outbox_id=event_id,
        tenant_id=tenant_id,
        store_id=store_id,
        aggregate_id=uuid4(),
        event_type="order_confirmed",
        payload={"order_id": "order-1"},
        available_at=datetime.now(timezone.utc),
    )
    calls = []
    set_outbox_delivery_handler(
        lambda event: calls.append(event["id"]) or OutboxDeliveryResult(success=True, delivery_id="delivery-1")
    )
    try:
        assert deliver_one_outbox(store=store) is not None
        assert deliver_outbox_by_id(store=store, outbox_id=event_id) is True
        assert calls == [event_id]
    finally:
        set_outbox_delivery_handler(None)
