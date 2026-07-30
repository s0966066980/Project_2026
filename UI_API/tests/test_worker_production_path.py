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


def test_rag_studio_index_handler_executes_publication_attempt(monkeypatch) -> None:
    from services import worker_handlers, worker_service

    calls = []

    class PublicationModule:
        def run_attempt(self, **kwargs):
            calls.append(kwargs)
            return {
                "attempt_id": kwargs["attempt_id"],
                "status": "published",
                "phase": "complete",
                "retryable": False,
            }

    monkeypatch.setattr(
        worker_handlers.knowledge_publication_runtime,
        "default_module",
        lambda: PublicationModule(),
    )
    store = worker_service.InMemoryJobStore()
    job = worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="rag.studio.index",
        payload_ref={"attempt_id": "attempt-breakfast-v2"},
        idempotency_key="rag-studio-index",
        store=store,
    )

    result = worker_handlers.handle_rag_studio_index(job)

    assert result.success is True
    assert result.side_effect_id == f"knowledge-publication:{STORE}:attempt-breakfast-v2"
    assert result.result_ref == "attempt-breakfast-v2"
    assert calls[0]["attempt_id"] == "attempt-breakfast-v2"
    assert calls[0]["scope"].tenant_id == TENANT
    assert calls[0]["scope"].store_id == STORE
    assert calls[0]["retry_budget_exhausted"] is False


def test_rag_studio_index_handler_delegates_retry_budget_to_publication_module(monkeypatch) -> None:
    from services import worker_handlers, worker_service

    store = worker_service.InMemoryJobStore()
    job = worker_service.enqueue_job(
        tenant_id=TENANT,
        store_id=STORE,
        job_type="rag.studio.index",
        payload_ref={"attempt_id": "attempt-broken"},
        idempotency_key="rag-studio-broken",
        store=store,
    )

    calls = []

    class PublicationModule:
        def run_attempt(self, **kwargs):
            calls.append(kwargs)
            exhausted = kwargs["retry_budget_exhausted"]
            return {
                "attempt_id": kwargs["attempt_id"],
                "status": "index_failed" if exhausted else "indexing",
                "phase": "build",
                "retryable": not exhausted,
            }

    monkeypatch.setattr(
        worker_handlers.knowledge_publication_runtime,
        "default_module",
        lambda: PublicationModule(),
    )
    retry_result = worker_handlers.handle_rag_studio_index(job)
    assert retry_result.success is False
    assert retry_result.retryable is True
    assert calls[0]["retry_budget_exhausted"] is False

    job.attempt_count = job.max_attempts
    terminal_result = worker_handlers.handle_rag_studio_index(job)
    assert terminal_result.success is False
    assert terminal_result.retryable is False
    assert terminal_result.safe_error == "index_failed"
    assert calls[1]["retry_budget_exhausted"] is True


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

def test_default_worker_store_uses_postgres_adapter_in_postgres_runtime(monkeypatch):
    from repositories import postgres_utils, postgres_worker_store
    from services import worker_service

    sentinel = object()
    monkeypatch.setattr(postgres_utils, "use_postgres", lambda: True)
    monkeypatch.setattr(postgres_worker_store, "PostgresJobStore", lambda: sentinel)

    assert worker_service.default_store() is sentinel
