"""Milestone 5A worker/outbox production path correctness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")


def test_unknown_handler_cannot_succeed() -> None:
    from models.worker_jobs import JobStatus
    from services import worker_service

    store = worker_service.InMemoryJobStore()
    worker_service.clear_handlers()
    worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="report.generate",
        payload_ref={"report_id": "daily"},
        idempotency_key="unknown-handler",
        store=store,
    )
    processed = worker_service.process_one_job(store=store, worker_id="w-unknown")
    assert processed is not None
    assert processed.status is JobStatus.DEAD_LETTER
    assert "unknown_handler" in processed.safe_error


def test_handler_without_side_effect_cannot_succeed() -> None:
    from models.worker_jobs import JobHandlerResult, JobStatus
    from services import worker_service

    store = worker_service.InMemoryJobStore()
    worker_service.register_handler(
        "report.generate",
        lambda _job: JobHandlerResult(success=True, retryable=False, safe_error=""),
    )
    try:
        worker_service.enqueue_job(
            tenant_id=TENANT,
            store_id=STORE,
            job_type="report.generate",
            payload_ref={"report_id": "daily"},
            idempotency_key="missing-side-effect",
            store=store,
        )
        processed = worker_service.process_one_job(store=store, worker_id="w-side-effect")
        assert processed is not None
        assert processed.status is JobStatus.DEAD_LETTER
        assert processed.safe_error == "handler_missing_side_effect"
    finally:
        worker_service.clear_handlers()


def test_production_handlers_execute_real_side_effects() -> None:
    from models.worker_jobs import JobStatus
    from services import worker_handlers, worker_service

    worker_handlers.clear_side_effect_ledger()
    worker_service.clear_handlers()
    worker_handlers.register_production_handlers()
    store = worker_service.InMemoryJobStore()
    worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="report.generate",
        payload_ref={"report_id": "ops-daily"},
        idempotency_key="ops-daily",
        store=store,
    )
    processed = worker_service.process_one_job(store=store, worker_id="w-prod")
    assert processed is not None
    assert processed.status is JobStatus.SUCCEEDED
    ledger = worker_handlers.side_effect_ledger()
    assert any(key.startswith("report:") for key in ledger)
    worker_service.clear_handlers()


def test_outbox_not_published_until_sink_ack() -> None:
    from models.worker_jobs import OutboxDeliveryResult
    from services import worker_service

    store = worker_service.InMemoryJobStore()
    outbox_id = uuid4()
    store.seed_outbox(
        outbox_id=outbox_id,
        tenant_id=TENANT,
        store_id=STORE,
        aggregate_id=uuid4(),
        event_type="order_confirmed",
        payload={"order_id": "o-ack-1", "status": "confirmed"},
    )

    attempts = {"count": 0}

    def flaky_sink(_event):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return OutboxDeliveryResult(success=False, retryable=True, safe_error="sink_timeout")
        return OutboxDeliveryResult(success=True, delivery_id=str(outbox_id), provider="test_sink")

    worker_service.set_outbox_delivery_handler(flaky_sink)
    try:
        base = datetime.now(timezone.utc)
        first = worker_service.deliver_one_outbox(store=store, worker_id="w-outbox", now=base)
        assert first is not None
        assert store.get_outbox(outbox_id)["published_at"] is None
        second = worker_service.deliver_one_outbox(
            store=store,
            worker_id="w-outbox",
            now=base + timedelta(seconds=120),
        )
        assert second is not None
        assert store.get_outbox(outbox_id)["published_at"] is not None
    finally:
        worker_service.set_outbox_delivery_handler(None)


def test_production_handler_registry_covers_allowed_job_types() -> None:
    from models.worker_jobs import ALLOWED_JOB_TYPES
    from services.worker_handler_registry import JobHandlerRegistry
    from services.worker_handlers import register_production_handlers

    registry = JobHandlerRegistry()
    register_production_handlers(registry=registry)
    registry.validate_required_handlers(ALLOWED_JOB_TYPES)
    assert set(registry.list_registered()) == set(ALLOWED_JOB_TYPES)


def test_run_worker_bootstrap_registers_required_handlers() -> None:
    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parents[1] / "backend" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import run_worker

    run_worker._bootstrap_production_worker()
    from services.worker_handler_registry import default_registry

    default_registry().validate_required_handlers()
