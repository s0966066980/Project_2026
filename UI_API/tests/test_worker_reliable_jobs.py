"""Milestone 2E reliable background worker and outbox delivery contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")


def test_worker_migration_defines_jobs_and_outbox_delivery_controls() -> None:
    sql = (ROOT / "UI_API/backend/schemas/migrations/0008_worker_reliable_async_jobs.sql").read_text(
        encoding="utf-8"
    )
    for fragment in (
        "CREATE TABLE background_jobs",
        "idempotency_key",
        "payload_ref",
        "dead_letter",
        "visibility_timeout_seconds",
        "locked_until",
        "ALTER TABLE order_outbox",
        "dead_lettered_at",
        "available_at",
        "max_attempts",
    ):
        assert fragment in sql
    assert "CREATE EXTENSION" not in sql.upper()


def test_job_contract_rejects_secret_payload_and_unknown_type() -> None:
    from models.worker_jobs import JobValidationError, validate_job_payload_ref
    from services import worker_service

    with pytest.raises(JobValidationError):
        validate_job_payload_ref({"password": "secret"})
    with pytest.raises(JobValidationError):
        validate_job_payload_ref({"token": "abc"})
    with pytest.raises(JobValidationError):
        worker_service.enqueue_job(
            tenant_id=TENANT,
            store_id=STORE,
            job_type="not.a.real.job",
            payload_ref={"object_id": "safe"},
            idempotency_key="k1",
            store=worker_service.InMemoryJobStore(),
        )


def test_job_contract_accepts_bounded_scalar_reference_lists() -> None:
    from models.worker_jobs import JobValidationError, validate_job_payload_ref

    payload = validate_job_payload_ref({"selected_source_ids": ["faq-a", "policy-b"]})
    assert payload["selected_source_ids"] == ["faq-a", "policy-b"]
    with pytest.raises(JobValidationError):
        validate_job_payload_ref({"selected_source_ids": [["nested"]]})


def test_enqueue_is_idempotent_and_does_not_block_on_handler() -> None:
    from models.worker_jobs import JobStatus
    from services import worker_service

    store = worker_service.InMemoryJobStore()
    first = worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="report.generate",
        payload_ref={"report_id": "r1"},
        idempotency_key="report-r1",
        store=store,
    )
    second = worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="report.generate",
        payload_ref={"report_id": "r1"},
        idempotency_key="report-r1",
        store=store,
    )
    assert first.job_id == second.job_id
    assert first.status is JobStatus.PENDING
    assert len(store.list_jobs()) == 1


def test_retry_backoff_then_dead_letter_for_poison_job() -> None:
    from models.worker_jobs import JobHandlerResult, JobStatus
    from services import observability_service, worker_service

    observability_service.reset_metrics_for_tests()
    store = worker_service.InMemoryJobStore()
    worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="ai.background",
        payload_ref={"task_id": "t1"},
        idempotency_key="ai-t1",
        max_attempts=3,
        store=store,
    )

    def always_fail(_job):
        return JobHandlerResult(
            success=False,
            retryable=True,
            safe_error="provider_timeout",
            side_effect_id="",
        )

    worker_service.register_handler("ai.background", always_fail)
    try:
        base = datetime.now(timezone.utc)
        for index in range(3):
            claimed = worker_service.process_one_job(
                store=store,
                worker_id="w1",
                now=base + timedelta(seconds=index * 120),
            )
            assert claimed is not None
        job = store.list_jobs()[0]
        assert job.status is JobStatus.DEAD_LETTER
        assert job.attempt_count == 3
        snapshot = observability_service.metrics_snapshot()
        assert snapshot["worker_jobs_retry_total"]["total"] >= 2
        assert snapshot["worker_jobs_dlq_total"]["total"] == 1
    finally:
        worker_service.clear_handlers()


def test_visibility_timeout_recovers_running_job_after_process_crash() -> None:
    from models.worker_jobs import JobHandlerResult, JobStatus
    from services import worker_service

    store = worker_service.InMemoryJobStore()
    worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="cleanup.retention",
        payload_ref={"scope": "logs"},
        idempotency_key="cleanup-1",
        visibility_timeout_seconds=30,
        store=store,
    )
    now = datetime.now(timezone.utc)

    def hang(_job):
        raise worker_service.SimulatedWorkerCrash("crash before ack")

    worker_service.register_handler("cleanup.retention", hang)
    try:
        with pytest.raises(worker_service.SimulatedWorkerCrash):
            worker_service.process_one_job(store=store, worker_id="w-crash", now=now)
        stuck = store.list_jobs()[0]
        assert stuck.status is JobStatus.RUNNING
        recovered = worker_service.process_one_job(
            store=store,
            worker_id="w-recover",
            now=now + timedelta(seconds=31),
            handler=lambda _job: JobHandlerResult(
                success=True,
                retryable=False,
                safe_error="",
                side_effect_id="recovery-side-effect",
            ),
        )
        assert recovered is not None
        assert store.list_jobs()[0].status is JobStatus.SUCCEEDED
    finally:
        worker_service.clear_handlers()


def test_outbox_delivery_is_idempotent_and_tenant_isolated() -> None:
    from services import observability_service, worker_service
    from services.outbox_delivery_router import configure_default_outbox_router

    configure_default_outbox_router()
    observability_service.reset_metrics_for_tests()
    store = worker_service.InMemoryJobStore()
    outbox_a = uuid4()
    outbox_b = uuid4()
    other_tenant = UUID("00000000-0000-4000-8000-000000000099")
    store.seed_outbox(
        outbox_id=outbox_a,
        tenant_id=TENANT,
        store_id=STORE,
        aggregate_id=uuid4(),
        event_type="order_confirmed",
        payload={"order_id": "o1", "status": "confirmed"},
    )
    store.seed_outbox(
        outbox_id=outbox_b,
        tenant_id=other_tenant,
        store_id=UUID("00000000-0000-4000-8000-000000000098"),
        aggregate_id=uuid4(),
        event_type="order_confirmed",
        payload={"order_id": "o2", "status": "confirmed"},
    )

    first = worker_service.deliver_one_outbox(store=store, worker_id="w1", tenant_filter=TENANT)
    assert first is not None
    assert first["id"] == outbox_a
    assert store.get_outbox(outbox_a)["published_at"] is not None
    # Re-delivery of published event is a no-op success path.
    assert worker_service.deliver_outbox_by_id(store=store, outbox_id=outbox_a, worker_id="w1") is True
    # Other tenant event remains unpublished until its own claim.
    assert store.get_outbox(outbox_b)["published_at"] is None
    other = worker_service.deliver_one_outbox(store=store, worker_id="w1", tenant_filter=other_tenant)
    assert other is not None and other["id"] == outbox_b


def test_outbox_poison_message_moves_to_dead_letter() -> None:
    from services import worker_service

    store = worker_service.InMemoryJobStore()
    outbox_id = uuid4()
    store.seed_outbox(
        outbox_id=outbox_id,
        tenant_id=TENANT,
        store_id=STORE,
        aggregate_id=uuid4(),
        event_type="order_completed",
        payload={"order_id": "bad"},
        max_attempts=2,
    )

    from models.worker_jobs import OutboxDeliveryResult

    def poison(_event):
        return OutboxDeliveryResult(success=False, retryable=True, safe_error="invalid_payload")

    worker_service.set_outbox_delivery_handler(poison)
    try:
        base = datetime.now(timezone.utc)
        worker_service.deliver_one_outbox(store=store, worker_id="w1", now=base)
        worker_service.deliver_one_outbox(store=store, worker_id="w1", now=base + timedelta(seconds=120))
        row = store.get_outbox(outbox_id)
        assert row["published_at"] is None
        assert row["dead_lettered_at"] is not None
        assert row["attempt_count"] == 2
    finally:
        worker_service.set_outbox_delivery_handler(None)


def test_worker_metrics_expose_depth_and_oldest_age() -> None:
    from services import observability_service, worker_service

    observability_service.reset_metrics_for_tests()
    store = worker_service.InMemoryJobStore()
    worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="event.deliver",
        payload_ref={"event_id": "e1"},
        idempotency_key="e1",
        store=store,
    )
    worker_service.refresh_queue_metrics(store=store)
    snapshot = observability_service.metrics_snapshot()
    assert snapshot["worker_jobs_depth"]["current"] == 1
    assert snapshot["worker_jobs_oldest_age_seconds"]["current"] >= 0
    assert snapshot["queue_backlog"]["current"] >= 1


def test_cancellation_prevents_further_execution() -> None:
    from models.worker_jobs import JobStatus
    from services import worker_service

    store = worker_service.InMemoryJobStore()
    job = worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="data.export",
        payload_ref={"export_id": "x1"},
        idempotency_key="x1",
        store=store,
    )
    assert worker_service.cancel_job(job.job_id, store=store) is True
    assert store.get_job(job.job_id).status is JobStatus.CANCELLED
    assert worker_service.process_one_job(store=store, worker_id="w1") is None
