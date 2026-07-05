"""RAG rebuild and health alert lifecycle."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import config

_lock = threading.Lock()


def _alerts_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "rag_alerts.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_alerts() -> list[dict]:
    try:
        data = json.loads(_alerts_path().read_text(encoding="utf-8"))
    except Exception:
        return []
    return [dict(row) for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _write_alerts(rows: list[dict]) -> None:
    path = _alerts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    max_records = max(100, int(config.get("RAG_ALERT_MAX_RECORDS", 1000)))
    tmp_path = path.with_suffix(f".json.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(json.dumps(rows[-max_records:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def _safe_errors(errors) -> list[dict]:
    rows = []
    for error in errors or []:
        if isinstance(error, dict):
            rows.append({
                "path": str(error.get("path") or ""),
                "source_id": str(error.get("source_id") or ""),
                "message": str(error.get("message") or "")[:1000],
            })
        else:
            rows.append({"message": str(error or "")[:1000]})
    return rows[:50]


def _fingerprint(alert_type: str, severity: str, message: str, source_dir: str, errors: list[dict]) -> str:
    raw = json.dumps({
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "source_dir": source_dir,
        "errors": errors[:10],
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def list_alerts(status: str = "", limit: int = 100) -> list[dict]:
    status_filter = str(status or "").strip().lower()
    safe_limit = max(1, min(int(limit or 100), 1000))
    with _lock:
        rows = _read_alerts()
    if status_filter:
        rows = [row for row in rows if str(row.get("status") or "") == status_filter]
    rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    return rows[:safe_limit]


def create_alert(
    alert_type: str,
    *,
    severity: str = "error",
    message: str = "",
    errors=None,
    source_dir: str = "",
    metadata: dict | None = None,
) -> tuple[dict, bool]:
    safe_errors = _safe_errors(errors)
    safe_type = str(alert_type or "rag_alert").strip() or "rag_alert"
    safe_severity = str(severity or "error").strip() or "error"
    safe_message = str(message or "").strip()[:1000] or "RAG alert"
    safe_source_dir = str(source_dir or "").strip()
    fingerprint = _fingerprint(safe_type, safe_severity, safe_message, safe_source_dir, safe_errors)
    now = _now_iso()
    with _lock:
        rows = _read_alerts()
        for index, row in enumerate(rows):
            if row.get("fingerprint") == fingerprint and row.get("status") in {"open", "acknowledged"}:
                row["last_seen_at"] = now
                row["updated_at"] = now
                row["count"] = int(row.get("count") or 1) + 1
                row["errors"] = safe_errors
                rows[index] = row
                _write_alerts(rows)
                return dict(row), False
        record = {
            "alert_id": f"rag_alert_{uuid4().hex}",
            "alert_type": safe_type,
            "severity": safe_severity,
            "status": "open",
            "message": safe_message,
            "errors": safe_errors,
            "source_dir": safe_source_dir,
            "metadata": metadata if isinstance(metadata, dict) else {},
            "fingerprint": fingerprint,
            "count": 1,
            "created_at": now,
            "updated_at": now,
            "last_seen_at": now,
            "acknowledged_at": "",
            "acknowledged_by": "",
            "resolved_at": "",
            "resolved_by": "",
            "notification": {},
        }
        rows.append(record)
        _write_alerts(rows)
    notification = notify_external(record)
    if notification:
        with _lock:
            rows = _read_alerts()
            for index, row in enumerate(rows):
                if row.get("alert_id") == record["alert_id"]:
                    row["notification"] = notification
                    row["updated_at"] = _now_iso()
                    rows[index] = row
                    record = dict(row)
                    _write_alerts(rows)
                    break
    return dict(record), True


def acknowledge_alert(alert_id: str, actor: str = "admin") -> tuple[dict | None, list[str]]:
    return _set_status(alert_id, "acknowledged", actor)


def resolve_alert(alert_id: str, actor: str = "admin") -> tuple[dict | None, list[str]]:
    return _set_status(alert_id, "resolved", actor)


def resolve_alerts_by_type(alert_type: str, actor: str = "system") -> int:
    now = _now_iso()
    count = 0
    with _lock:
        rows = _read_alerts()
        for row in rows:
            if row.get("alert_type") == alert_type and row.get("status") in {"open", "acknowledged"}:
                row["status"] = "resolved"
                row["resolved_at"] = now
                row["resolved_by"] = actor
                row["updated_at"] = now
                count += 1
        if count:
            _write_alerts(rows)
    return count


def _set_status(alert_id: str, status: str, actor: str) -> tuple[dict | None, list[str]]:
    safe_id = str(alert_id or "")
    now = _now_iso()
    with _lock:
        rows = _read_alerts()
        for index, row in enumerate(rows):
            if row.get("alert_id") != safe_id:
                continue
            row["status"] = status
            row["updated_at"] = now
            if status == "acknowledged":
                row["acknowledged_at"] = now
                row["acknowledged_by"] = str(actor or "admin")
            if status == "resolved":
                row["resolved_at"] = now
                row["resolved_by"] = str(actor or "admin")
            rows[index] = row
            _write_alerts(rows)
            return dict(row), []
    return None, ["alert_id 不存在"]


def notify_external(alert: dict) -> dict:
    if not config.get("RAG_ALERT_WEBHOOK_ENABLED", False):
        return {"enabled": False}
    webhook_url = str(config.get("RAG_ALERT_WEBHOOK_URL", "") or "").strip()
    if not webhook_url:
        return {"enabled": True, "status": "skipped", "message": "RAG_ALERT_WEBHOOK_URL not configured"}
    payload = json.dumps({"event": "rag_alert", "alert": alert}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = str(config.get("RAG_ALERT_WEBHOOK_TOKEN", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(webhook_url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=float(config.get("RAG_ALERT_WEBHOOK_TIMEOUT_SEC", 5))) as response:
            return {"enabled": True, "status": "sent", "http_status": response.status}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"enabled": True, "status": "failed", "message": str(exc)[:500]}
