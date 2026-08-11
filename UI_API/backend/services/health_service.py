"""Commercial operations health summary."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from modules.runtime_persistence.evidence import inspect_persistence

import config
from repositories import postgres_utils, recommendation_event_repository
from services import observability_service, shared_infrastructure_service
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


def _postgres_health(evidence: dict | None = None) -> dict:
    profile = evidence or inspect_persistence()
    status = "ok" if profile.get("status") == "ok" else "degraded"
    return {"name": "postgres", "status": status, **profile}


def _database_readiness(evidence: dict | None = None) -> dict:
    profile = evidence or inspect_persistence()
    status = "ok" if profile.get("status") == "ok" else "failed"
    observability_service.increment_metric(
        "postgres_operations_total", status="ready_success" if status == "ok" else "ready_failure"
    )
    return {
        "status": status,
        "error_code": profile.get("error_code", "") if status == "failed" else "",
        "configured_backend": profile.get("configured_backend", ""),
        "effective_backend": profile.get("effective_backend", ""),
        "topology": profile.get("topology", ""),
        "endpoint": profile.get("endpoint", {}),
        "connection": profile.get("connection", {}),
        "adapter_coverage": profile.get("adapter_coverage", {}),
    }


def _migration_readiness(evidence: dict | None = None) -> dict:
    schema = dict((evidence or inspect_persistence()).get("schema") or {})
    if schema.get("status") != "ok":
        observability_service.increment_metric("migration_validation_failures_total", status="not_clean")
        return {"status": "failed", "error_code": schema.get("error_code", "migration_not_clean"), **schema}
    return schema


def _scope_readiness() -> dict:
    if postgres_utils.storage_backend() != "postgresql":
        return {"status": "skipped", "reason": "local_sqlite_runtime"}
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
        message = (
            ""
            if fresh
            else (
                "no recommendation events recorded"
                if not events
                else "latest recommendation event is stale or missing a timestamp"
            )
        )
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


def _overall_status(checks: dict) -> str:
    unhealthy = {"degraded", "failed", "not_ready"}
    return "degraded" if any(check.get("status") in unhealthy for check in checks.values()) else "ok"


_INCIDENT_GUIDE = {
    "database": (
        "資料庫無法安全使用",
        "點餐、結帳、會員與管理寫入可能失敗。",
        "值班技術人員",
        "確認資料庫連線與 DATABASE_URL，勿切換到 JSON。",
    ),
    "migration": (
        "資料庫版本未就緒",
        "商業資料結構可能與目前程式不相容。",
        "值班技術人員",
        "停止寫入並確認 forward migration 狀態。",
    ),
    "commercial_scope": (
        "門市資料範圍未就緒",
        "可能無法保證資料只屬於目前門市。",
        "系統管理員",
        "確認 tenant、store 與 device 的有效關聯。",
    ),
    "shared_infrastructure": (
        "共用基礎設施未就緒",
        "多程序下的 session、限流或事件協調可能不一致。",
        "值班技術人員",
        "依 readiness error code 檢查共用基礎設施。",
    ),
    "postgres": (
        "商業資料庫異常",
        "會員、訂單、活動與管理寫入可能失敗。",
        "值班技術人員",
        "確認資料庫連線、migration 與儲存 backend。",
    ),
    "recommendation_events": (
        "推薦成效量測降級",
        "推薦仍可運作，但今日成效與歸因可能不可靠。",
        "店長",
        "確認 Kiosk 是否持續送出事件及最後事件時間。",
    ),
    "runtime_logs": (
        "問題追查能力降級",
        "顧客流程通常可繼續，但故障證據可能不完整。",
        "值班技術人員",
        "檢查不可解析記錄、磁碟空間與保留設定。",
    ),
}


def _incident_id(key: str, check: dict) -> str:
    evidence = {
        "key": key,
        "status": check.get("status"),
        "error_code": check.get("error_code"),
        "reason": check.get("reason"),
        "message": check.get("message"),
    }
    digest = sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"health_{key}_{digest}"


def build_operational_health(checks: dict, readiness: dict, incident_actions: list[dict] | None = None) -> dict:
    """Translate technical checks into an operator-facing health interface."""

    actions_by_incident: dict[str, dict] = {}
    for row in incident_actions or []:
        if row.get("target_type") != "health_incident":
            continue
        incident_id = str(row.get("target_id") or "")
        if incident_id:
            actions_by_incident[incident_id] = row

    incident_checks = {
        key: check
        for key, check in (readiness.get("required_checks") or {}).items()
        if check.get("status") not in {"ok", "skipped"}
    }
    incident_checks.update(
        {key: check for key, check in checks.items() if check.get("status") in {"degraded", "failed", "not_ready"}}
    )
    incidents = []
    for key, check in incident_checks.items():
        title, impact, owner, action = _INCIDENT_GUIDE.get(
            key,
            (f"{key} 檢查異常", "部分功能可能降級。", "值班技術人員", "依檢查證據與操作手冊處理。"),
        )
        incident_id = _incident_id(key, check)
        latest_action = actions_by_incident.get(incident_id, {})
        action_name = str(latest_action.get("action") or "")
        incidents.append(
            {
                "incident_id": incident_id,
                "check_key": key,
                "severity": "critical" if key in (readiness.get("required_checks") or {}) else "warning",
                "title": title,
                "impact": impact,
                "suggested_action": action,
                "owner": owner,
                "status": (
                    "escalated"
                    if action_name == "health.incident.escalate"
                    else "acknowledged"
                    if action_name == "health.incident.acknowledge"
                    else "open"
                ),
                "last_action_at": latest_action.get("created_at"),
                "last_actor": latest_action.get("actor", ""),
            }
        )

    if not readiness.get("ready"):
        state = "unsafe_to_operate"
        headline = "目前不可安全營運"
        impact = "必要的資料或門市範圍檢查未通過，應停止建立新的商業寫入。"
    elif incidents:
        state = "operate_with_degraded_features"
        headline = "可以營運，但部分功能降級"
        impact = "點餐與結帳必要條件已通過；請依事件卡處理受影響的選用功能。"
    else:
        state = "safe_to_operate"
        headline = "目前可以正常營運"
        impact = "必要條件與本次選用功能檢查均正常。"

    required_ready = bool(readiness.get("ready"))
    measurement_ok = checks.get("recommendation_events", {}).get("status") == "ok"
    return {
        "state": state,
        "headline": headline,
        "business_impact": impact,
        "capabilities": [
            {
                "key": "ordering_checkout",
                "label": "點餐與結帳",
                "status": "available" if required_ready else "unavailable",
            },
            {
                "key": "member_service",
                "label": "會員查詢與服務",
                "status": "available" if required_ready else "unavailable",
            },
            {
                "key": "recommendation_measurement",
                "label": "推薦成效量測",
                "status": "available" if measurement_ok else "degraded",
            },
        ],
        "incidents": incidents,
    }


async def build_admin_health(incident_actions: list[dict] | None = None) -> dict:
    checks = {
        "postgres": _postgres_health(),
        "runtime_logs": _runtime_health(),
        "recommendation_events": _recommendation_health(),
    }

    readiness = build_readiness()
    operational = build_operational_health(checks, readiness, incident_actions)
    return {
        "status": _overall_status(checks) if readiness.get("ready") else "not_ready",
        "generated_at": datetime.now().isoformat(),
        "app": {
            "environment": config.APP_ENV,
            "security_enforced": config.is_security_enforced(),
            "database_backend": postgres_utils.storage_backend(),
            "structured_logging_enabled": bool(config.get("STRUCTURED_LOGGING_ENABLED", True)),
        },
        "checks": checks,
        "readiness": readiness,
        "operational": operational,
        "metrics": observability_service.metrics_snapshot(),
    }
