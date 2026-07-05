"""Commercial operations health summary."""
from __future__ import annotations

from datetime import datetime

import config
from repositories import postgres_utils, recommendation_event_repository
from services import observability_service, rag_alert_service, rag_document_service


def _ok(name: str, **details) -> dict:
    return {"name": name, "status": "ok", **details}


def _skipped(name: str, reason: str, **details) -> dict:
    return {"name": name, "status": "skipped", "reason": reason, **details}


def _degraded(name: str, message: str, **details) -> dict:
    return {"name": name, "status": "degraded", "message": message, **details}


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


def _runtime_health() -> dict:
    logs = observability_service.runtime_log_stats()
    unreadable = [
        row for row in logs
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
        recent = events[-200:]
        event_types = {}
        for event in recent:
            event_type = str(event.get("event_type") or "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1
        return _ok(
            "recommendation_events",
            sampled_records=len(events),
            recent_records=len(recent),
            recent_event_types=event_types,
        )
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
    return "degraded" if any(check.get("status") == "degraded" for check in checks.values()) else "ok"


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

    return {
        "status": _overall_status(checks),
        "generated_at": datetime.now().isoformat(),
        "app": {
            "environment": config.APP_ENV,
            "security_enforced": config.is_security_enforced(),
            "member_storage_backend": postgres_utils.storage_backend(),
            "structured_logging_enabled": bool(config.get("STRUCTURED_LOGGING_ENABLED", True)),
        },
        "checks": checks,
    }
