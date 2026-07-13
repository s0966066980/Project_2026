"""PostgreSQL integration for commercial readiness and observability gates."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_readiness_uses_clean_database_scope_and_outbox_without_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    from repositories import postgres_utils
    from services import health_service, observability_service

    base_url = postgres_utils.database_url()
    schema = "observability_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)
    monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "postgres")
    monkeypatch.setattr(health_service.postgres_utils, "database_url", lambda: scoped_url)
    monkeypatch.setattr(health_service.postgres_utils, "storage_backend", lambda: "postgres")
    monkeypatch.setattr(
        health_service.rag_document_service,
        "health_status",
        lambda: pytest.fail("AI/RAG health must not be called by basic readiness"),
    )
    postgres_utils.init_schema()
    observability_service.reset_metrics_for_tests()
    ready = health_service.build_readiness()
    assert ready["ready"] is True, ready
    assert ready["required_checks"]["migration"]["status"] == "ok"
    assert ready["required_checks"]["commercial_scope"]["status"] == "ok"
    assert observability_service.metrics_snapshot()["order_outbox_pending"]["current"] == 0

    monkeypatch.setattr(
        health_service.postgres_utils,
        "connect",
        lambda: (_ for _ in ()).throw(postgres_utils.PostgresUnavailableError("unavailable")),
    )
    unavailable = health_service.build_readiness()
    assert unavailable["ready"] is False
    assert unavailable["required_checks"]["database"] == {
        "status": "failed",
        "error_code": "database_unavailable",
    }
