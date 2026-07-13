"""PostgreSQL integration for reliable worker jobs and outbox delivery."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_worker_jobs_and_outbox_delivery_on_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from models.worker_jobs import JobStatus
    from repositories import checkout_order_repository, postgres_utils, worker_job_repository
    from services import observability_service
    from services.checkout_service import checkout_request_fingerprint

    base_url = postgres_utils.database_url()
    schema = "worker_jobs_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)
    monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "postgres")
    postgres_utils.init_schema()

    priced = {
        "cart_ids": ["meal"],
        "cart_items": [
            {
                "id": "meal",
                "name": "Meal",
                "category": "main",
                "quantity": 1,
                "base_unit_price": 100,
                "option_unit_total": 0,
                "discount_unit_total": 0,
                "final_unit_price": 100,
                "price": 100,
                "options": [],
            }
        ],
        "subtotal": 100,
        "option_total": 0,
        "discount_total": 0,
        "tax_total": 0,
        "total": 100,
        "currency": "TWD",
        "calculation_version": "checkout-v1",
    }
    fingerprint = checkout_request_fingerprint("worker-session", priced)
    order = checkout_order_repository.create_checkout_order_scoped(
        LEGACY_DEFAULT_SCOPE,
        "worker-session",
        "worker-idem-1",
        fingerprint,
        priced,
    )
    order_id = UUID(str(order["order_id"]))

    job = worker_job_repository.enqueue_job(
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        store_id=LEGACY_DEFAULT_SCOPE.store_id,
        job_type="report.generate",
        payload_ref={"report_id": "daily"},
        idempotency_key="daily-report",
    )
    again = worker_job_repository.enqueue_job(
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        store_id=LEGACY_DEFAULT_SCOPE.store_id,
        job_type="report.generate",
        payload_ref={"report_id": "daily"},
        idempotency_key="daily-report",
    )
    assert job.job_id == again.job_id

    claimed = worker_job_repository.claim_next_job(worker_id="ci-worker")
    assert claimed is not None
    assert claimed.status is JobStatus.RUNNING
    completed = worker_job_repository.complete_job(claimed.job_id)
    assert completed is not None
    assert completed.status is JobStatus.SUCCEEDED

    outbox = worker_job_repository.claim_next_outbox(worker_id="ci-worker")
    assert outbox is not None
    assert outbox["aggregate_id"] == order_id
    worker_job_repository.mark_outbox_published(outbox["id"])
    assert worker_job_repository.claim_next_outbox(worker_id="ci-worker") is None

    metrics = worker_job_repository.queue_metrics()
    assert metrics.pending_outbox == 0
    observability_service.set_metric("order_outbox_pending", metrics.pending_outbox)
    assert observability_service.metrics_snapshot()["order_outbox_pending"]["current"] == 0
