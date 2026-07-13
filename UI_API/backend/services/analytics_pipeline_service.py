"""Replayable analytics event envelope and idempotent sink adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import config


class AnalyticsError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "analytics_events.json"


def _checkpoints_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "analytics_checkpoints.json"


@dataclass
class InMemoryAnalyticsSink:
    events: list[dict[str, Any]] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)

    def write(self, envelope: dict[str, Any]) -> bool:
        event_id = str(envelope.get("event_id") or "")
        if not event_id:
            raise AnalyticsError("event_id_required")
        if event_id in self.seen:
            return False
        self.seen.add(event_id)
        self.events.append(envelope)
        return True


def build_envelope(
    *,
    event_type: str,
    payload: dict[str, Any],
    tenant_id: UUID,
    store_id: UUID | None = None,
    session_ref: str = "",
    order_ref: str = "",
    member_ref: str = "",
    source: str = "api",
    schema_version: str = "analytics-v1",
    event_id: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    if any(key in payload for key in ("phone", "password", "token", "card_number")):
        raise AnalyticsError("payload_contains_forbidden_fields")
    return {
        "event_id": event_id or f"ae_{uuid4().hex}",
        "type": event_type,
        "schema_version": schema_version,
        "occurred_at": occurred_at or _now(),
        "received_at": _now(),
        "scope": {
            "tenant_id": str(tenant_id),
            "store_id": str(store_id) if store_id else None,
        },
        "session_ref": session_ref,
        "order_ref": order_ref,
        "member_ref": member_ref,
        "payload": dict(payload or {}),
        "source": source,
    }


def event_already_persisted(event_id: str) -> bool:
    normalized = str(event_id or "").strip()
    if not normalized:
        return False
    path = _path()
    if not path.exists():
        return False
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(rows, list):
        return False
    return any(str(row.get("event_id") or "") == normalized for row in rows if isinstance(row, dict))


def publish(envelope: dict[str, Any], *, sink: InMemoryAnalyticsSink | None = None) -> bool:
    active = sink or InMemoryAnalyticsSink()
    accepted = active.write(envelope)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = []
    if accepted:
        existing.append(envelope)
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return accepted


def replay(
    *,
    event_type: str | None = None,
    tenant_id: UUID | None = None,
    since: str | None = None,
    sink: InMemoryAnalyticsSink | None = None,
) -> int:
    path = _path()
    if not path.exists():
        return 0
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(rows, list):
        return 0
    active = sink or InMemoryAnalyticsSink()
    count = 0
    for row in rows:
        if event_type and row.get("type") != event_type:
            continue
        if tenant_id and (row.get("scope") or {}).get("tenant_id") != str(tenant_id):
            continue
        if since and str(row.get("occurred_at") or "") < since:
            continue
        if active.write(row):
            count += 1
    checkpoint = {
        "replayed_at": _now(),
        "count": count,
        "event_type": event_type,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "since": since,
    }
    cp = _checkpoints_path()
    cp.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return count


def data_quality(rows: list[dict[str, Any]]) -> dict[str, int]:
    seen: set[str] = set()
    duplicates = 0
    missing = 0
    unknown_version = 0
    for row in rows:
        event_id = str(row.get("event_id") or "")
        if not event_id:
            missing += 1
        elif event_id in seen:
            duplicates += 1
        else:
            seen.add(event_id)
        if str(row.get("schema_version") or "") not in {"analytics-v1"}:
            unknown_version += 1
    return {
        "duplicates": duplicates,
        "missing_event_id": missing,
        "unknown_schema_version": unknown_version,
        "total": len(rows),
    }
