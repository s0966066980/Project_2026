"""PostgreSQL integration for production worker handler and outbox ACK paths."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_postgres_worker_executes_handler_before_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from models.worker_jobs import JobStatus
    from repositories import checkout_order_repository, postgres_utils, worker_job_repository
    from repositories.postgres_worker_store import PostgresJobStore
    from services import worker_handlers, worker_service
    from repositories.checkout_order_repository import checkout_request_fingerprint
    from services.outbox_delivery_router import configure_default_outbox_router

    base_url = postgres_utils.database_url()
    schema = "worker_production_path_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)
    monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "postgres")
    postgres_utils.init_schema()

    worker_handlers.clear_side_effect_ledger()
    worker_service.clear_handlers()
    worker_handlers.register_production_handlers()
    configure_default_outbox_router()
    store = PostgresJobStore()

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
    fingerprint = checkout_request_fingerprint("worker-production-session", priced)
    order = checkout_order_repository.create_checkout_order_scoped(
        LEGACY_DEFAULT_SCOPE,
        "worker-production-session",
        "worker-production-idem",
        fingerprint,
        priced,
    )
    order_id = UUID(str(order["order_id"]))

    worker_job_repository.enqueue_job(
        tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
        store_id=LEGACY_DEFAULT_SCOPE.store_id,
        job_type="report.generate",
        payload_ref={"report_id": "pg-daily"},
        idempotency_key="pg-daily-report",
    )

    summary = worker_service.run_worker_cycle(store=store, worker_id="pg-worker", max_jobs=5, max_outbox=5)
    assert summary["jobs_processed"] == 1
    assert summary["outbox_processed"] == 1

    jobs = worker_job_repository.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is JobStatus.SUCCEEDED
    assert worker_handlers.side_effect_ledger()

    outbox_rows = worker_job_repository.claim_next_outbox(worker_id="pg-worker-2")
    assert outbox_rows is None
    outbox = worker_job_repository.get_outbox_by_aggregate(order_id)
    assert outbox is not None
    assert outbox["published_at"] is not None
    assert outbox["aggregate_id"] == order_id
