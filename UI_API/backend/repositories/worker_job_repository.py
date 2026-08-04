"""PostgreSQL adapter for durable background jobs and order_outbox delivery."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from models.worker_jobs import BackgroundJob, JobStatus, QueueMetrics, compute_backoff_seconds, validate_job_payload_ref
from repositories import postgres_utils
from services import observability_service


def _jsonb(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _row_to_job(row: dict[str, Any]) -> BackgroundJob:
    return BackgroundJob(
        job_id=row["id"],
        tenant_id=row["tenant_id"],
        store_id=row.get("store_id"),
        job_type=str(row["job_type"]),
        payload_ref=dict(row.get("payload_ref") or {}),
        status=JobStatus(str(row["status"])),
        attempt_count=int(row.get("attempt_count") or 0),
        max_attempts=int(row.get("max_attempts") or 5),
        idempotency_key=str(row["idempotency_key"]),
        scheduled_at=row["scheduled_at"],
        available_at=row["available_at"],
        visibility_timeout_seconds=int(row.get("visibility_timeout_seconds") or 60),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        locked_by=row.get("locked_by"),
        locked_until=row.get("locked_until"),
        safe_error=str(row.get("safe_error") or ""),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def get_job(job_id: UUID) -> BackgroundJob | None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM background_jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
    return _row_to_job(row) if row else None


def list_jobs() -> list[BackgroundJob]:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM background_jobs ORDER BY scheduled_at ASC")
        rows = cur.fetchall() or []
    return [_row_to_job(row) for row in rows]


def get_outbox(outbox_id: UUID) -> dict[str, Any] | None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM order_outbox WHERE id = %s", (outbox_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_outbox_by_aggregate(aggregate_id: UUID) -> dict[str, Any] | None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM order_outbox
            WHERE aggregate_id = %s
            ORDER BY occurred_at ASC
            LIMIT 1
            """,
            (aggregate_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def seed_outbox(
    *,
    outbox_id: UUID,
    tenant_id: UUID,
    store_id: UUID,
    aggregate_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    max_attempts: int = 5,
) -> None:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO order_outbox (
                id, tenant_id, store_id, aggregate_id, event_type, payload,
                attempt_count, max_attempts, available_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, 0, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                outbox_id,
                tenant_id,
                store_id,
                aggregate_id,
                event_type,
                _jsonb(payload),
                max_attempts,
                now,
            ),
        )
        conn.commit()


def enqueue_job(
    *,
    tenant_id: UUID,
    store_id: UUID | None,
    job_type: str,
    payload_ref: dict[str, Any] | None,
    idempotency_key: str,
    max_attempts: int = 5,
    visibility_timeout_seconds: int = 60,
) -> BackgroundJob:
    payload = validate_job_payload_ref(payload_ref)
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO background_jobs (
                id, tenant_id, store_id, job_type, payload_ref, status, attempt_count,
                max_attempts, idempotency_key, scheduled_at, available_at,
                visibility_timeout_seconds, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s::jsonb, 'pending', 0,
                %s, %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (tenant_id, job_type, idempotency_key) DO NOTHING
            RETURNING *
            """,
            (
                job_id,
                tenant_id,
                store_id,
                job_type,
                _jsonb(payload),
                max_attempts,
                idempotency_key,
                now,
                now,
                visibility_timeout_seconds,
                now,
                now,
            ),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                SELECT * FROM background_jobs
                WHERE tenant_id = %s AND job_type = %s AND idempotency_key = %s
                """,
                (tenant_id, job_type, idempotency_key),
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise RuntimeError("Failed to enqueue background job")
    return _row_to_job(row)


def claim_next_job(*, worker_id: str, tenant_filter: UUID | None = None) -> BackgroundJob | None:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        if tenant_filter is None:
            cur.execute(
                """
                SELECT id FROM background_jobs
                WHERE status IN ('pending', 'running', 'failed')
                  AND available_at <= %s
                  AND (locked_until IS NULL OR locked_until <= %s)
                  AND status <> 'cancelled'
                ORDER BY available_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (now, now),
            )
        else:
            cur.execute(
                """
                SELECT id FROM background_jobs
                WHERE tenant_id = %s
                  AND status IN ('pending', 'running', 'failed')
                  AND available_at <= %s
                  AND (locked_until IS NULL OR locked_until <= %s)
                  AND status <> 'cancelled'
                ORDER BY available_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (tenant_filter, now, now),
            )
        selected = cur.fetchone()
        if selected is None:
            conn.commit()
            return None
        job_id = selected["id"]
        cur.execute(
            """
            UPDATE background_jobs
            SET status = 'running',
                attempt_count = attempt_count + 1,
                started_at = COALESCE(started_at, %s),
                locked_by = %s,
                locked_until = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (
                now,
                worker_id,
                now + timedelta(seconds=60),
                now,
                job_id,
            ),
        )
        row = cur.fetchone()
        # Recompute locked_until from row visibility after update when available.
        if row is not None:
            timeout = int(row.get("visibility_timeout_seconds") or 60)
            cur.execute(
                """
                UPDATE background_jobs
                SET locked_until = %s
                WHERE id = %s
                RETURNING *
                """,
                (now + timedelta(seconds=timeout), job_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_job(row) if row else None


def complete_job(job_id: UUID, *, safe_error: str = "") -> BackgroundJob | None:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE background_jobs
            SET status = 'succeeded',
                finished_at = %s,
                locked_by = NULL,
                locked_until = NULL,
                safe_error = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (now, safe_error[:500], now, job_id),
        )
        row = cur.fetchone()
        conn.commit()
    return _row_to_job(row) if row else None


def fail_job(job_id: UUID, *, safe_error: str, retryable: bool) -> BackgroundJob | None:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM background_jobs WHERE id = %s FOR UPDATE", (job_id,))
        current = cur.fetchone()
        if current is None:
            conn.commit()
            return None
        attempt = int(current["attempt_count"] or 0)
        max_attempts = int(current["max_attempts"] or 5)
        if retryable and attempt < max_attempts:
            status = "pending"
            finished_at = None
            available_at = now + timedelta(seconds=compute_backoff_seconds(attempt))
        else:
            status = "dead_letter"
            finished_at = now
            available_at = current["available_at"]
        cur.execute(
            """
            UPDATE background_jobs
            SET status = %s,
                finished_at = %s,
                available_at = %s,
                locked_by = NULL,
                locked_until = NULL,
                safe_error = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (
                status,
                finished_at,
                available_at,
                observability_service.redact_sensitive_text(safe_error)[:500],
                now,
                job_id,
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return _row_to_job(row) if row else None


def cancel_job(job_id: UUID) -> BackgroundJob | None:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE background_jobs
            SET status = 'cancelled',
                finished_at = %s,
                locked_by = NULL,
                locked_until = NULL,
                updated_at = %s
            WHERE id = %s
              AND status NOT IN ('succeeded', 'dead_letter', 'cancelled')
            RETURNING *
            """,
            (now, now, job_id),
        )
        row = cur.fetchone()
        conn.commit()
    return _row_to_job(row) if row else None


def queue_metrics() -> QueueMetrics:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status IN ('pending', 'running', 'failed')) AS depth,
                COUNT(*) FILTER (WHERE status = 'dead_letter') AS dead_letter_count,
                MIN(scheduled_at) FILTER (WHERE status IN ('pending', 'running', 'failed')) AS oldest
            FROM background_jobs
            """
        )
        job_row = cur.fetchone() or {}
        cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM order_outbox
            WHERE published_at IS NULL AND dead_lettered_at IS NULL
            """
        )
        outbox_row = cur.fetchone() or {}
    oldest = job_row.get("oldest")
    oldest_age = max(0.0, (now - oldest).total_seconds()) if oldest is not None else 0.0
    return QueueMetrics(
        depth=int(job_row.get("depth") or 0),
        oldest_age_seconds=oldest_age,
        dead_letter_count=int(job_row.get("dead_letter_count") or 0),
        pending_outbox=int(outbox_row.get("count") or 0),
    )


def claim_next_outbox(*, worker_id: str, tenant_filter: UUID | None = None) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        if tenant_filter is None:
            cur.execute(
                """
                SELECT id FROM order_outbox
                WHERE published_at IS NULL
                  AND dead_lettered_at IS NULL
                  AND available_at <= %s
                  AND (locked_until IS NULL OR locked_until <= %s)
                ORDER BY available_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (now, now),
            )
        else:
            cur.execute(
                """
                SELECT id FROM order_outbox
                WHERE tenant_id = %s
                  AND published_at IS NULL
                  AND dead_lettered_at IS NULL
                  AND available_at <= %s
                  AND (locked_until IS NULL OR locked_until <= %s)
                ORDER BY available_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (tenant_filter, now, now),
            )
        selected = cur.fetchone()
        if selected is None:
            conn.commit()
            return None
        cur.execute(
            """
            UPDATE order_outbox
            SET attempt_count = attempt_count + 1,
                locked_by = %s,
                locked_until = %s
            WHERE id = %s
            RETURNING *
            """,
            (worker_id, now + timedelta(seconds=60), selected["id"]),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def mark_outbox_published(outbox_id: UUID) -> None:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE order_outbox
            SET published_at = %s,
                locked_by = NULL,
                locked_until = NULL,
                last_error = ''
            WHERE id = %s AND published_at IS NULL
            """,
            (now, outbox_id),
        )
        conn.commit()


def mark_outbox_failed(outbox_id: UUID, *, safe_error: str, retryable: bool = True) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM order_outbox WHERE id = %s FOR UPDATE", (outbox_id,))
        current = cur.fetchone()
        if current is None:
            conn.commit()
            return None
        attempt = int(current["attempt_count"] or 0)
        max_attempts = int(current.get("max_attempts") or 5)
        if not retryable or attempt >= max_attempts:
            cur.execute(
                """
                UPDATE order_outbox
                SET dead_lettered_at = %s,
                    locked_by = NULL,
                    locked_until = NULL,
                    last_error = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, observability_service.redact_sensitive_text(safe_error)[:500], outbox_id),
            )
        else:
            cur.execute(
                """
                UPDATE order_outbox
                SET available_at = %s,
                    locked_by = NULL,
                    locked_until = NULL,
                    last_error = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    now + timedelta(seconds=compute_backoff_seconds(attempt)),
                    observability_service.redact_sensitive_text(safe_error)[:500],
                    outbox_id,
                ),
            )
        row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None
