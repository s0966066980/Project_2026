"""Commercial operations health summary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
from repositories import postgres_utils, recommendation_event_repository
from services import observability_service, rag_alert_service, rag_document_service, shared_infrastructure_service
from services.commercial_scope_readiness_service import validate_configured_commercial_scope


def _ok(name: str, **details) -> dict:
    return {"name": name, "status": "ok", **details}


def _skipped(name: str, reason: str, **details) -> dict:
    return {"name": name, "status": "skipped", "reason": reason, **details}


def _degraded(name: str, message: str, **details) -> dict:
    return {
        "name": name,
        "status": "degraded",
        "message": observability_service.redact_sensitive_text(message)[:500],
        **details,
    }


def _postgres_health() -> dict:
    backend = postgres_utils.storage_backend()
    if backend != "postgres":
        return _skipped("postgres", "MEMBER_STORAGE_BACKEND is not postgres", backend=backend)
    try:
        postgres_utils.init_schema()
        with postgres_utils.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS value")
                ping = cur.fetchone() or {}
                cur.execute(
                    """
                    SELECT version, applied_at
                    FROM schema_migrations
                    ORDER BY applied_at DESC, version DESC
                    LIMIT 1
                    """
                )
                latest = cur.fetchone() or {}
                cur.execute("SELECT COUNT(*) AS value FROM schema_migrations")
                count_row = cur.fetchone() or {}
        return _ok(
            "postgres",
            backend=backend,
            ping=ping.get("value") == 1,
            schema_migration_count=int(count_row.get("value", 0) or 0),
            latest_schema_migration={
                "version": str(latest.get("version") or ""),
                "applied_at": str(latest.get("applied_at") or ""),
            },
        )
    except Exception as exc:
        return _degraded("postgres", str(exc)[:500], backend=backend)


def _database_readiness() -> dict:
    backend = postgres_utils.storage_backend()
    if backend != "postgres":
        if config.APP_ENV in {"production", "staging"}:
            return {"status": "failed", "error_code": "postgres_required"}
        return {"status": "skipped", "reason": "json_compatibility_backend"}
    try:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 AS value")
            if (cur.fetchone() or {}).get("value") != 1:
                raise RuntimeError
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM order_outbox
                WHERE published_at IS NULL AND dead_lettered_at IS NULL
                """
            )
            pending_outbox = int((cur.fetchone() or {}).get("count") or 0)
            try:
                cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM background_jobs
                    WHERE status IN ('pending', 'running', 'failed')
                    """
                )
                job_depth = int((cur.fetchone() or {}).get("count") or 0)
            except Exception:
                job_depth = 0
        observability_service.increment_metric("postgres_operations_total", status="ready_success")
        observability_service.set_metric("order_outbox_pending", pending_outbox)
        observability_service.set_metric("worker_jobs_depth", job_depth)
        observability_service.set_metric("queue_backlog", pending_outbox + job_depth)
        return {"status": "ok", "pending_outbox": pending_outbox, "worker_jobs_depth": job_depth}
    except Exception:
        observability_service.increment_metric("postgres_operations_total", status="ready_failure")
        return {"status": "failed", "error_code": "database_unavailable"}


def _migration_readiness() -> dict:
    if postgres_utils.storage_backend() != "postgres":
        return {"status": "skipped", "reason": "json_compatibility_backend"}
    try:
        plan = postgres_utils.get_migration_plan()
        postgres_utils.validate_migration_plan(plan, require_clean=True)
        return {"status": "ok", "applied_count": len(plan.applied_versions)}
    except Exception:
        observability_service.increment_metric("migration_validation_failures_total", status="not_clean")
        return {"status": "failed", "error_code": "migration_not_clean"}


def _scope_readiness() -> dict:
    if postgres_utils.storage_backend() != "postgres":
        return {"status": "skipped", "reason": "json_compatibility_backend"}
    try:
        validate_configured_commercial_scope()
        return {"status": "ok"}
    except Exception:
        return {"status": "failed", "error_code": "commercial_scope_not_ready"}


def build_readiness() -> dict:
    required_checks = {
        "database": _database_readiness(),
        "migration": _migration_readiness(),
        "commercial_scope": _scope_readiness(),
        "shared_infrastructure": shared_infrastructure_service.readiness(),
    }
    ready = all(check.get("status") in {"ok", "skipped"} for check in required_checks.values())
    return {
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "required_checks": required_checks,
        "degraded_optional_dependencies": ["llm", "emotion", "rag"],
    }


def _runtime_health() -> dict:
    logs = observability_service.runtime_log_stats()
    unreadable = [
        row
        for row in logs
        if row.get("exists") and int(row.get("records", 0) or 0) == 0 and int(row.get("size_bytes", 0) or 0) > 2
    ]
    status = "degraded" if unreadable else "ok"
    return {
        "name": "runtime_logs",
        "status": status,
        "retention_days": int(config.get("LOG_RETENTION_DAYS", 90) or 0),
        "last_retention": observability_service.last_retention_summary(),
        "logs": logs,
        "warnings": [
            {"name": row.get("name", ""), "message": "file exists but could not be parsed as JSON list"}
            for row in unreadable
        ],
    }


def _recommendation_health() -> dict:
    try:
        events = recommendation_event_repository.get_recommendation_events(limit=5000)
        latest_sample = events[-200:]
        event_types: dict[str, int] = {}
        for event in latest_sample:
            event_type = str(event.get("event_type") or "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1
        freshness_hours = max(1, int(config.get("RECOMMENDATION_EVENT_FRESHNESS_HOURS", 24) or 24))
        timestamps = []
        for event in events:
            raw_timestamp = event.get("timestamp") or event.get("occurred_at") or event.get("created_at")
            if not raw_timestamp:
                continue
            try:
                parsed = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            except ValueError:
                continue
            timestamps.append(parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc))
        latest = max(timestamps) if timestamps else None
        fresh = latest is not None and latest >= datetime.now(timezone.utc) - timedelta(hours=freshness_hours)
        status = "ok" if fresh else "degraded"
        message = "" if fresh else ("no recommendation events recorded" if not events else "latest recommendation event is stale or missing a timestamp")
        return {
            "name": "recommendation_events",
            "status": status,
            "message": message,
            "sampled_records": len(events),
            "latest_sampled_records": len(latest_sample),
            "latest_event_at": latest.isoformat() if latest else "",
            "freshness_hours": freshness_hours,
            "recent_event_types": event_types,
        }
    except Exception as exc:
        return _degraded("recommendation_events", str(exc)[:500])


def _rag_alert_health() -> dict:
    try:
        open_alerts = rag_alert_service.list_alerts(status="open", limit=1000)
        acknowledged = rag_alert_service.list_alerts(status="acknowledged", limit=1000)
        status = "degraded" if open_alerts else "ok"
        return {
            "name": "rag_alerts",
            "status": status,
            "open_count": len(open_alerts),
            "acknowledged_count": len(acknowledged),
            "latest_open_alert": open_alerts[0] if open_alerts else {},
        }
    except Exception as exc:
        return _degraded("rag_alerts", str(exc)[:500])


def _overall_status(checks: dict) -> str:
    unhealthy = {"degraded", "failed", "not_ready"}
    return "degraded" if any(check.get("status") in unhealthy for check in checks.values()) else "ok"


async def build_admin_health() -> dict:
    checks = {
        "postgres": _postgres_health(),
        "runtime_logs": _runtime_health(),
        "recommendation_events": _recommendation_health(),
        "rag_alerts": _rag_alert_health(),
    }
    try:
        rag_health = await rag_document_service.health_status()
        checks["rag"] = {"name": "rag", **rag_health}
    except Exception as exc:
        checks["rag"] = _degraded("rag", str(exc)[:500])

    readiness = build_readiness()
    return {
        "status": _overall_status(checks) if readiness.get("ready") else "not_ready",
        "generated_at": datetime.now().isoformat(),
        "app": {
            "environment": config.APP_ENV,
            "security_enforced": config.is_security_enforced(),
            "member_storage_backend": postgres_utils.storage_backend(),
            "structured_logging_enabled": bool(config.get("STRUCTURED_LOGGING_ENABLED", True)),
        },
        "checks": checks,
        "readiness": readiness,
        "metrics": observability_service.metrics_snapshot(),
    }
