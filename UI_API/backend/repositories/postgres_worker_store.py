"""PostgreSQL JobStore adapter for the production worker service path."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from models.worker_jobs import BackgroundJob, QueueMetrics
from repositories import worker_job_repository


class PostgresJobStore:
    """Bridges worker_service JobStore protocol to PostgreSQL repositories."""

    def enqueue(self, job: BackgroundJob) -> BackgroundJob:
        return worker_job_repository.enqueue_job(
            tenant_id=job.tenant_id,
            store_id=job.store_id,
            job_type=job.job_type,
            payload_ref=job.payload_ref,
            idempotency_key=job.idempotency_key,
            max_attempts=job.max_attempts,
            visibility_timeout_seconds=job.visibility_timeout_seconds,
        )

    def get_job(self, job_id: UUID) -> BackgroundJob | None:
        return worker_job_repository.get_job(job_id)

    def list_jobs(self) -> list[BackgroundJob]:
        return worker_job_repository.list_jobs()

    def claim_next(self, *, worker_id: str, now: datetime, tenant_filter: UUID | None = None) -> BackgroundJob | None:
        del now
        return worker_job_repository.claim_next_job(worker_id=worker_id, tenant_filter=tenant_filter)

    def complete(self, job_id: UUID, *, now: datetime, safe_error: str = "") -> BackgroundJob | None:
        del now
        return worker_job_repository.complete_job(job_id, safe_error=safe_error)

    def fail(
        self,
        job_id: UUID,
        *,
        now: datetime,
        safe_error: str,
        retryable: bool,
    ) -> BackgroundJob | None:
        del now
        return worker_job_repository.fail_job(job_id, safe_error=safe_error, retryable=retryable)

    def cancel(self, job_id: UUID, *, now: datetime) -> BackgroundJob | None:
        del now
        return worker_job_repository.cancel_job(job_id)

    def metrics(self, *, now: datetime) -> QueueMetrics:
        del now
        return worker_job_repository.queue_metrics()

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
        available_at: datetime | None = None,
    ) -> None:
        worker_job_repository.seed_outbox(
            outbox_id=outbox_id,
            tenant_id=tenant_id,
            store_id=store_id,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            max_attempts=max_attempts,
            available_at=available_at,
        )

    def claim_outbox(
        self, *, worker_id: str, now: datetime, tenant_filter: UUID | None = None
    ) -> dict[str, Any] | None:
        del now
        return worker_job_repository.claim_next_outbox(worker_id=worker_id, tenant_filter=tenant_filter)

    def get_outbox(self, outbox_id: UUID) -> dict[str, Any] | None:
        return worker_job_repository.get_outbox(outbox_id)

    def mark_outbox_published(self, outbox_id: UUID, *, now: datetime) -> None:
        del now
        worker_job_repository.mark_outbox_published(outbox_id)

    def mark_outbox_failed(
        self,
        outbox_id: UUID,
        *,
        now: datetime,
        safe_error: str,
        retryable: bool = True,
    ) -> dict[str, Any] | None:
        del now
        return worker_job_repository.mark_outbox_failed(outbox_id, safe_error=safe_error, retryable=retryable)
