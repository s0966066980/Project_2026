"""Reliable background worker: enqueue, claim, retry, DLQ, and outbox delivery."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Callable, Protocol
from uuid import UUID, uuid4

from models.worker_jobs import (
    BackgroundJob,
    JobHandlerResult,
    JobStatus,
    JobValidationError,
    OutboxDeliveryResult,
    QueueMetrics,
    compute_backoff_seconds,
    validate_job_payload_ref,
    validate_job_type,
)
from services import observability_service
from services.outbox_delivery_router import OutboxDeliveryRouter, default_router
from services.worker_handler_registry import JobHandler, JobHandlerRegistry, default_registry

_OUTBOX_ROUTER_LOCK = Lock()
_TEST_OUTBOX_HANDLER: Callable[[dict[str, Any]], OutboxDeliveryResult] | None = None


class SimulatedWorkerCrash(RuntimeError):
    """Test-only signal that the worker process crashed before acknowledgement."""


class JobStore(Protocol):
    def enqueue(self, job: BackgroundJob) -> BackgroundJob: ...

    def get_job(self, job_id: UUID) -> BackgroundJob | None: ...

    def list_jobs(self) -> list[BackgroundJob]: ...

    def claim_next(
        self, *, worker_id: str, now: datetime, tenant_filter: UUID | None = None
    ) -> BackgroundJob | None: ...

    def complete(self, job_id: UUID, *, now: datetime, safe_error: str = "") -> BackgroundJob | None: ...

    def fail(
        self,
        job_id: UUID,
        *,
        now: datetime,
        safe_error: str,
        retryable: bool,
    ) -> BackgroundJob | None: ...

    def cancel(self, job_id: UUID, *, now: datetime) -> BackgroundJob | None: ...

    def metrics(self, *, now: datetime) -> QueueMetrics: ...

    def seed_outbox(
        self,
        *,
        outbox_id: UUID,
        tenant_id: UUID,
        store_id: UUID,
        aggregate_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        max_attempts: int = 5,
    ) -> None: ...

    def claim_outbox(
        self, *, worker_id: str, now: datetime, tenant_filter: UUID | None = None
    ) -> dict[str, Any] | None: ...

    def get_outbox(self, outbox_id: UUID) -> dict[str, Any] | None: ...

    def mark_outbox_published(self, outbox_id: UUID, *, now: datetime) -> None: ...

    def mark_outbox_failed(
        self,
        outbox_id: UUID,
        *,
        now: datetime,
        safe_error: str,
        retryable: bool = True,
    ) -> dict[str, Any] | None: ...


class InMemoryJobStore:
    """Process-local durable job/outbox store used by unit tests and pure service paths."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, BackgroundJob] = {}
        self._outbox: dict[UUID, dict[str, Any]] = {}
        self._lock = Lock()

    def enqueue(self, job: BackgroundJob) -> BackgroundJob:
        with self._lock:
            for existing in self._jobs.values():
                if (
                    existing.tenant_id == job.tenant_id
                    and existing.job_type == job.job_type
                    and existing.idempotency_key == job.idempotency_key
                ):
                    return copy.deepcopy(existing)
            self._jobs[job.job_id] = copy.deepcopy(job)
            return copy.deepcopy(job)

    def get_job(self, job_id: UUID) -> BackgroundJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return copy.deepcopy(job) if job else None

    def list_jobs(self) -> list[BackgroundJob]:
        with self._lock:
            return [copy.deepcopy(job) for job in self._jobs.values()]

    def claim_next(self, *, worker_id: str, now: datetime, tenant_filter: UUID | None = None) -> BackgroundJob | None:
        with self._lock:
            candidates = sorted(
                (
                    job
                    for job in self._jobs.values()
                    if (tenant_filter is None or job.tenant_id == tenant_filter)
                    and job.status
                    in {
                        JobStatus.PENDING,
                        JobStatus.RUNNING,
                        JobStatus.FAILED,
                    }
                    and job.available_at <= now
                    and (job.locked_until is None or job.locked_until <= now)
                ),
                key=lambda item: item.available_at,
            )
            if not candidates:
                return None
            job = candidates[0]
            if job.status is JobStatus.CANCELLED:
                return None
            job.status = JobStatus.RUNNING
            job.attempt_count += 1
            job.started_at = now
            job.locked_by = worker_id
            job.locked_until = now + timedelta(seconds=job.visibility_timeout_seconds)
            job.updated_at = now
            return copy.deepcopy(job)

    def complete(self, job_id: UUID, *, now: datetime, safe_error: str = "") -> BackgroundJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = JobStatus.SUCCEEDED
            job.finished_at = now
            job.locked_by = None
            job.locked_until = None
            job.safe_error = safe_error
            job.updated_at = now
            return copy.deepcopy(job)

    def fail(
        self,
        job_id: UUID,
        *,
        now: datetime,
        safe_error: str,
        retryable: bool,
    ) -> BackgroundJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.safe_error = safe_error[:500]
            job.locked_by = None
            job.locked_until = None
            job.updated_at = now
            if retryable and job.attempt_count < job.max_attempts:
                job.status = JobStatus.PENDING
                job.available_at = now + timedelta(seconds=compute_backoff_seconds(job.attempt_count))
                job.finished_at = None
            else:
                job.status = JobStatus.DEAD_LETTER
                job.finished_at = now
            return copy.deepcopy(job)

    def cancel(self, job_id: UUID, *, now: datetime) -> BackgroundJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in {JobStatus.SUCCEEDED, JobStatus.DEAD_LETTER, JobStatus.CANCELLED}:
                return copy.deepcopy(job)
            job.status = JobStatus.CANCELLED
            job.finished_at = now
            job.locked_by = None
            job.locked_until = None
            job.updated_at = now
            return copy.deepcopy(job)

    def metrics(self, *, now: datetime) -> QueueMetrics:
        with self._lock:
            open_jobs = [
                job
                for job in self._jobs.values()
                if job.status in {JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED}
            ]
            dead = sum(1 for job in self._jobs.values() if job.status is JobStatus.DEAD_LETTER)
            pending_outbox = sum(
                1
                for row in self._outbox.values()
                if row.get("published_at") is None and row.get("dead_lettered_at") is None
            )
            if not open_jobs:
                oldest = 0.0
            else:
                oldest = max(0.0, (now - min(job.scheduled_at for job in open_jobs)).total_seconds())
            return QueueMetrics(
                depth=len(open_jobs),
                oldest_age_seconds=oldest,
                dead_letter_count=dead,
                pending_outbox=pending_outbox,
            )

    def seed_outbox(
        self,
        *,
        outbox_id: UUID,
        tenant_id: UUID,
        store_id: UUID,
        aggregate_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        max_attempts: int = 5,
    ) -> None:
        with self._lock:
            self._outbox[outbox_id] = {
                "id": outbox_id,
                "tenant_id": tenant_id,
                "store_id": store_id,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": dict(payload),
                "attempt_count": 0,
                "max_attempts": max_attempts,
                "available_at": datetime.now(timezone.utc),
                "locked_by": None,
                "locked_until": None,
                "last_error": "",
                "published_at": None,
                "dead_lettered_at": None,
            }

    def claim_outbox(
        self, *, worker_id: str, now: datetime, tenant_filter: UUID | None = None
    ) -> dict[str, Any] | None:
        with self._lock:
            candidates = sorted(
                (
                    row
                    for row in self._outbox.values()
                    if row["published_at"] is None
                    and row["dead_lettered_at"] is None
                    and row["available_at"] <= now
                    and (row["locked_until"] is None or row["locked_until"] <= now)
                    and (tenant_filter is None or row["tenant_id"] == tenant_filter)
                ),
                key=lambda item: item["available_at"],
            )
            if not candidates:
                return None
            row = candidates[0]
            row["attempt_count"] = int(row["attempt_count"]) + 1
            row["locked_by"] = worker_id
            row["locked_until"] = now + timedelta(seconds=60)
            return copy.deepcopy(row)

    def get_outbox(self, outbox_id: UUID) -> dict[str, Any] | None:
        with self._lock:
            row = self._outbox.get(outbox_id)
            return copy.deepcopy(row) if row else None

    def mark_outbox_published(self, outbox_id: UUID, *, now: datetime) -> None:
        with self._lock:
            row = self._outbox.get(outbox_id)
            if row is None:
                return
            row["published_at"] = now
            row["locked_by"] = None
            row["locked_until"] = None
            row["last_error"] = ""

    def mark_outbox_failed(
        self,
        outbox_id: UUID,
        *,
        now: datetime,
        safe_error: str,
        retryable: bool = True,
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self._outbox.get(outbox_id)
            if row is None:
                return None
            row["last_error"] = safe_error[:500]
            row["locked_by"] = None
            row["locked_until"] = None
            if not retryable or int(row["attempt_count"]) >= int(row["max_attempts"]):
                row["dead_lettered_at"] = now
            else:
                row["available_at"] = now + timedelta(seconds=compute_backoff_seconds(int(row["attempt_count"])))
            return copy.deepcopy(row)


_DEFAULT_STORE = InMemoryJobStore()


def default_store() -> InMemoryJobStore:
    return _DEFAULT_STORE


def handler_registry() -> JobHandlerRegistry:
    return default_registry()


def outbox_router() -> OutboxDeliveryRouter:
    return default_router()


def register_handler(job_type: str, handler: JobHandler) -> None:
    default_registry().register(job_type, handler)


def clear_handlers() -> None:
    default_registry().clear()


def set_outbox_delivery_handler(
    handler: Callable[[dict[str, Any]], OutboxDeliveryResult] | Callable[[dict[str, Any]], tuple[bool, str]] | None,
) -> None:
    global _TEST_OUTBOX_HANDLER
    if handler is None:
        _TEST_OUTBOX_HANDLER = None
        return

    def wrapped(event: dict[str, Any]) -> OutboxDeliveryResult:
        result = handler(event)
        if isinstance(result, OutboxDeliveryResult):
            return result
        ok, safe_error = result
        return OutboxDeliveryResult(success=bool(ok), safe_error=str(safe_error or ""), retryable=not ok)

    _TEST_OUTBOX_HANDLER = wrapped


def _resolve_handler(job_type: str, override: JobHandler | None = None) -> JobHandler | None:
    if override is not None:
        return override
    return default_registry().resolve(job_type)


def _unknown_handler(job: BackgroundJob) -> JobHandlerResult:
    observability_service.increment_metric("worker_unknown_handler", status=job.job_type)
    return JobHandlerResult(success=False, retryable=False, safe_error="unknown_handler")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_job(
    *,
    tenant_id: UUID,
    store_id: UUID | None,
    job_type: str,
    payload_ref: dict[str, Any] | None,
    idempotency_key: str,
    max_attempts: int = 5,
    visibility_timeout_seconds: int = 60,
    store: JobStore | None = None,
    scheduled_at: datetime | None = None,
) -> BackgroundJob:
    store = store or default_store()
    normalized_type = validate_job_type(job_type)
    payload = validate_job_payload_ref(payload_ref)
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 200:
        raise JobValidationError("idempotency_key is required and must be <= 200 characters")
    if max_attempts < 1:
        raise JobValidationError("max_attempts must be positive")
    if visibility_timeout_seconds < 1:
        raise JobValidationError("visibility_timeout_seconds must be positive")
    now = scheduled_at or _now()
    job = BackgroundJob(
        job_id=uuid4(),
        tenant_id=tenant_id,
        store_id=store_id,
        job_type=normalized_type,
        payload_ref=payload,
        status=JobStatus.PENDING,
        attempt_count=0,
        max_attempts=max_attempts,
        idempotency_key=key,
        scheduled_at=now,
        available_at=now,
        visibility_timeout_seconds=visibility_timeout_seconds,
        created_at=now,
        updated_at=now,
    )
    return store.enqueue(job)


def cancel_job(job_id: UUID, *, store: JobStore | None = None) -> bool:
    store = store or default_store()
    result = store.cancel(job_id, now=_now())
    return result is not None and result.status is JobStatus.CANCELLED


def process_one_job(
    *,
    store: JobStore | None = None,
    worker_id: str = "worker",
    now: datetime | None = None,
    handler: JobHandler | None = None,
    tenant_filter: UUID | None = None,
) -> BackgroundJob | None:
    store = store or default_store()
    clock = now or _now()
    job = store.claim_next(worker_id=worker_id, now=clock, tenant_filter=tenant_filter)
    if job is None:
        return None
    active_handler = _resolve_handler(job.job_type, handler)
    if active_handler is None:
        active_handler = _unknown_handler
    observability_service.increment_metric("worker_job_started", status=job.job_type)
    try:
        result = active_handler(job)
    except SimulatedWorkerCrash:
        # Leave the job running so visibility timeout can reclaim it.
        raise
    except Exception as exc:  # noqa: BLE001 - boundary: convert to safe retryable failure
        result = JobHandlerResult(
            success=False,
            retryable=True,
            safe_error=observability_service.redact_sensitive_text(str(exc))[:200],
        )
    if result.success:
        if not result.side_effect_id:
            failed = store.fail(
                job.job_id,
                now=clock,
                safe_error="handler_missing_side_effect",
                retryable=False,
            )
            observability_service.increment_metric("worker_job_failed", status="no_side_effect")
            refresh_queue_metrics(store=store, now=clock)
            return failed
        completed = store.complete(job.job_id, now=clock, safe_error="")
        observability_service.increment_metric("worker_jobs_success_total")
        observability_service.increment_metric("worker_job_succeeded", status=job.job_type)
        refresh_queue_metrics(store=store, now=clock)
        return completed
    failed = store.fail(
        job.job_id,
        now=clock,
        safe_error=observability_service.redact_sensitive_text(result.safe_error or "job_failed")[:200],
        retryable=result.retryable,
    )
    if failed and failed.status is JobStatus.DEAD_LETTER:
        observability_service.increment_metric("worker_jobs_dlq_total")
        observability_service.increment_metric("worker_job_dlq", status=job.job_type)
        observability_service.increment_metric("worker_jobs_failure_total", status="dead_letter")
        observability_service.increment_metric("worker_job_failed", status="dead_letter")
    else:
        observability_service.increment_metric("worker_jobs_retry_total")
        observability_service.increment_metric("worker_job_retry", status=job.job_type)
        observability_service.increment_metric("worker_jobs_failure_total", status="retry")
        observability_service.increment_metric("worker_job_failed", status="retry")
    refresh_queue_metrics(store=store, now=clock)
    return failed


def deliver_one_outbox(
    *,
    store: JobStore | None = None,
    worker_id: str = "worker",
    now: datetime | None = None,
    tenant_filter: UUID | None = None,
) -> dict[str, Any] | None:
    store = store or default_store()
    clock = now or _now()
    event = store.claim_outbox(worker_id=worker_id, now=clock, tenant_filter=tenant_filter)
    if event is None:
        return None
    return _finish_outbox_delivery(store=store, event=event, now=clock)


def deliver_outbox_by_id(
    *,
    store: JobStore | None = None,
    outbox_id: UUID,
    worker_id: str = "worker",
    now: datetime | None = None,
) -> bool:
    """Idempotent re-delivery: already published events succeed without re-running side effects."""

    store = store or default_store()
    clock = now or _now()
    row = store.get_outbox(outbox_id)
    if row is None:
        return False
    if row.get("published_at") is not None:
        return True
    if row.get("dead_lettered_at") is not None:
        return False
    claimed = store.claim_outbox(worker_id=worker_id, now=clock, tenant_filter=row["tenant_id"])
    if claimed is None or claimed["id"] != outbox_id:
        # Another worker may have claimed a different event first; try direct completion path.
        latest = store.get_outbox(outbox_id)
        if latest and latest.get("published_at") is not None:
            return True
        return False
    _finish_outbox_delivery(store=store, event=claimed, now=clock)
    latest = store.get_outbox(outbox_id)
    return bool(latest and latest.get("published_at") is not None)


def _finish_outbox_delivery(
    *,
    store: JobStore,
    event: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    with _OUTBOX_ROUTER_LOCK:
        test_handler = _TEST_OUTBOX_HANDLER
    if test_handler is not None:
        try:
            result = test_handler(event)
        except Exception as exc:  # noqa: BLE001 - boundary
            result = OutboxDeliveryResult(
                success=False,
                retryable=True,
                safe_error=observability_service.redact_sensitive_text(str(exc))[:200],
            )
    else:
        result = default_router().deliver(event)
    if result.success:
        store.mark_outbox_published(event["id"], now=now)
        observability_service.increment_metric("worker_jobs_success_total", status="outbox")
        refresh_queue_metrics(store=store, now=now)
        published = store.get_outbox(event["id"]) or event
        return published
    failed = store.mark_outbox_failed(
        event["id"],
        now=now,
        safe_error=observability_service.redact_sensitive_text(result.safe_error or "outbox_delivery_failed")[:200],
        retryable=result.retryable,
    )
    if failed and failed.get("dead_lettered_at") is not None:
        observability_service.increment_metric("worker_jobs_dlq_total", status="outbox")
    else:
        observability_service.increment_metric("worker_jobs_retry_total", status="outbox")
    refresh_queue_metrics(store=store, now=now)
    return failed or event


def refresh_queue_metrics(*, store: JobStore | None = None, now: datetime | None = None) -> QueueMetrics:
    store = store or default_store()
    clock = now or _now()
    metrics = store.metrics(now=clock)
    observability_service.set_metric("worker_jobs_depth", metrics.depth)
    observability_service.set_metric("worker_jobs_oldest_age_seconds", metrics.oldest_age_seconds)
    observability_service.set_metric("order_outbox_pending", metrics.pending_outbox)
    observability_service.set_metric("queue_backlog", metrics.depth + metrics.pending_outbox)
    return metrics


def run_worker_cycle(
    *,
    store: JobStore | None = None,
    worker_id: str = "worker",
    max_jobs: int = 10,
    max_outbox: int = 10,
    now: datetime | None = None,
) -> dict[str, int]:
    """Process a bounded batch of jobs and outbox events without blocking the API process."""

    store = store or default_store()
    clock = now or _now()
    jobs_processed = 0
    outbox_processed = 0
    for _ in range(max(0, max_jobs)):
        if process_one_job(store=store, worker_id=worker_id, now=clock) is None:
            break
        jobs_processed += 1
    for _ in range(max(0, max_outbox)):
        if deliver_one_outbox(store=store, worker_id=worker_id, now=clock) is None:
            break
        outbox_processed += 1
    refresh_queue_metrics(store=store, now=clock)
    return {"jobs_processed": jobs_processed, "outbox_processed": outbox_processed}


def job_as_public_dict(job: BackgroundJob) -> dict[str, Any]:
    return {
        "job_id": str(job.job_id),
        "tenant_id": str(job.tenant_id),
        "store_id": str(job.store_id) if job.store_id else None,
        "job_type": job.job_type,
        "payload_ref": dict(job.payload_ref),
        "status": job.status.value,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "idempotency_key": job.idempotency_key,
        "safe_error": job.safe_error,
    }
