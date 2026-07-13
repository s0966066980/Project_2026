"""Structured logging and runtime retention helpers."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import config

LOGGER_NAME = "ui_api"
REQUEST_LOGGER_NAME = "ui_api.request"
_CONFIGURED = False
_LAST_RETENTION_SUMMARY: dict = {}
_CORRELATION_CONTEXT: ContextVar[dict[str, str]] = ContextVar("correlation_context", default={})
_METRICS_LOCK = Lock()
REQUIRED_METRICS = (
    "http_requests_total",
    "websocket_connections_total",
    "checkout_attempts_total",
    "checkout_idempotency_replays_total",
    "postgres_operations_total",
    "migration_validation_failures_total",
    "auth_failures_total",
    "device_auth_failures_total",
    "llm_provider_requests_total",
    "emotion_evidence_total",
    "intervention_outcomes_total",
    "order_outbox_pending",
    "queue_backlog",
)
_METRICS: dict[str, dict[str, float]] = {name: defaultdict(float) for name in REQUIRED_METRICS}
_PHONE_PATTERN = re.compile(r"(?<!\d)09\d{8}(?!\d)")
_DATABASE_URL_PATTERN = re.compile(r"(?:postgres(?:ql)?|mysql)://[^\s]+", re.IGNORECASE)
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|authorization|api[_-]?key|database_url)\b\s*[=:]\s*[^\s,;]+"
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        context = correlation_context()
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": redact_sensitive_text(record.getMessage()),
        }
        for key in (
            "request_id",
            "trace_id",
            "tenant_id",
            "store_id",
            "device_id",
            "error_code",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client_host",
            "event",
        ):
            value = getattr(record, key, None) or context.get(key)
            if value not in (None, ""):
                payload[key] = redact_sensitive_text(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def redact_sensitive_text(value: object) -> str:
    text = str(value or "")
    text = _DATABASE_URL_PATTERN.sub("[REDACTED]", text)
    text = _CREDENTIAL_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return _PHONE_PATTERN.sub("[REDACTED]", text)


def correlation_context() -> dict[str, str]:
    return dict(_CORRELATION_CONTEXT.get())


def bind_correlation_context(**values: object) -> Token:
    current = correlation_context()
    current.update({key: str(value) for key, value in values.items() if value not in (None, "")})
    return _CORRELATION_CONTEXT.set(current)


def reset_correlation_context(token: Token) -> None:
    _CORRELATION_CONTEXT.reset(token)


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex}"


def safe_correlation_id(value: str | None, *, prefix: str) -> str:
    candidate = str(value or "").strip()
    if candidate and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", candidate):
        return candidate
    return new_request_id() if prefix == "req" else new_trace_id()


def increment_metric(name: str, value: float = 1, *, status: str = "total") -> None:
    if name not in _METRICS:
        raise ValueError("Metric name is not registered")
    label = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(status or "total"))[:80]
    with _METRICS_LOCK:
        _METRICS[name][label] += float(value)


def set_metric(name: str, value: float, *, status: str = "current") -> None:
    if name not in _METRICS:
        raise ValueError("Metric name is not registered")
    label = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(status or "current"))[:80]
    with _METRICS_LOCK:
        _METRICS[name][label] = float(value)


def metrics_snapshot() -> dict[str, dict[str, float]]:
    with _METRICS_LOCK:
        return {name: dict(values) for name, values in _METRICS.items()}


def reset_metrics_for_tests() -> None:
    with _METRICS_LOCK:
        for values in _METRICS.values():
            values.clear()


def _bool_setting(name: str, default: bool) -> bool:
    value = config.get(name, default)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    return default


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    if not _bool_setting("STRUCTURED_LOGGING_ENABLED", True):
        _CONFIGURED = True
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    handler.setLevel(logging.INFO)

    root_logger = logging.getLogger(LOGGER_NAME)
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [
        existing for existing in root_logger.handlers if getattr(existing, "_ui_api_structured", False) is not True
    ]
    handler._ui_api_structured = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)
    root_logger.propagate = False
    _CONFIGURED = True


def request_logger() -> logging.Logger:
    configure_logging()
    return logging.getLogger(REQUEST_LOGGER_NAME)


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:16]}"


def log_request(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_host: str = "",
    trace_id: str = "",
    tenant_id: str = "",
    store_id: str = "",
    device_id: str = "",
) -> None:
    increment_metric("http_requests_total", status=f"{int(status_code) // 100}xx")
    request_logger().info(
        "http_request",
        extra={
            "event": "http_request",
            "request_id": request_id,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "store_id": store_id,
            "device_id": device_id,
            "method": method,
            "path": path,
            "status_code": int(status_code),
            "error_code": f"http_{int(status_code) // 100}xx" if int(status_code) >= 400 else "",
            "duration_ms": round(float(duration_ms), 2),
            "client_host": _masked_client_host(client_host),
        },
    )


def _masked_client_host(value: str) -> str:
    host = str(value or "")
    parts = host.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        return ".".join((*parts[:3], "0"))
    return "local" if host in {"localhost", "::1"} else ("[REDACTED]" if host else "")


def monotonic_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def _retention_days() -> int:
    try:
        return int(config.get("LOG_RETENTION_DAYS", 90))
    except Exception:
        return 90


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _record_timestamp(row: Any) -> datetime | None:
    if not isinstance(row, dict):
        return None
    for key in ("timestamp", "created_at", "updated_at", "result_updated_at"):
        parsed = _parse_timestamp(row.get(key))
        if parsed:
            return parsed
    return None


def _runtime_log_paths() -> list[Path]:
    base = Path(config.LEARNING_DATA_DIR)
    return [
        base / "session_logs.json",
        base / "interaction_events.json",
        base / "intervention_logs.json",
        base / "recommendation_events.json",
        base / "emotion_intervention_logs.json",
        base / "admin_audit_logs.json",
        base / "rag_alerts.json",
        base / "rag_reviews.json",
    ]


def _read_json_list(path: Path) -> list:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _write_json_list(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=4)
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def apply_runtime_retention(now: datetime | None = None) -> dict:
    global _LAST_RETENTION_SUMMARY
    days = _retention_days()
    if days <= 0:
        _LAST_RETENTION_SUMMARY = {"enabled": False, "retention_days": days, "files": []}
        return dict(_LAST_RETENTION_SUMMARY)

    current = now or datetime.now()
    cutoff = current - timedelta(days=days)
    results = []
    for path in _runtime_log_paths():
        rows = _read_json_list(path)
        if not rows:
            continue
        kept = []
        removed = 0
        for row in rows:
            parsed = _record_timestamp(row)
            if parsed is not None and parsed < cutoff:
                removed += 1
                continue
            kept.append(row)
        if removed:
            _write_json_list(path, kept)
        results.append(
            {
                "path": str(path),
                "before": len(rows),
                "after": len(kept),
                "removed": removed,
            }
        )
    summary = {"enabled": True, "retention_days": days, "files": results}
    _LAST_RETENTION_SUMMARY = dict(summary)
    logging.getLogger(LOGGER_NAME).info(
        "runtime_retention_applied",
        extra={"event": "runtime_retention_applied"},
    )
    return summary


def last_retention_summary() -> dict:
    return dict(_LAST_RETENTION_SUMMARY)


def runtime_log_stats() -> list[dict]:
    rows = []
    for path in _runtime_log_paths():
        records = _read_json_list(path)
        try:
            stat = path.stat()
            exists = True
            size_bytes = int(stat.st_size)
            modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except OSError:
            exists = False
            size_bytes = 0
            modified_at = ""
        latest = ""
        parsed_times: list[datetime] = [
            value for value in (_record_timestamp(row) for row in records) if isinstance(value, datetime)
        ]
        if parsed_times:
            latest = max(parsed_times).isoformat()
        rows.append(
            {
                "name": path.name,
                "path": str(path),
                "exists": exists,
                "records": len(records),
                "size_bytes": size_bytes,
                "modified_at": modified_at,
                "latest_record_at": latest,
            }
        )
    return rows
