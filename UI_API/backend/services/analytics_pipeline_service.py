"""Replayable analytics event envelope and idempotent sink adapter.

PostgreSQL analytics_event_log is the durable sink when MEMBER_STORAGE_BACKEND=postgres.
JSON / in-memory remain development and unit-test compatibility only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

import config
from repositories import postgres_utils


class AnalyticsError(ValueError):
    pass


_FORBIDDEN_KEYS = frozenset(
    {
        "phone",
        "email",
        "password",
        "token",
        "card",
        "card_number",
        "address",
        "raw_media",
        "ssn",
        "cvv",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "analytics_events.json"


def _checkpoints_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "analytics_checkpoints.json"


def reject_forbidden_payload(value: Any, *, path: str = "payload") -> None:
    """Recursive PII/secret key scan — not top-level only."""

    if isinstance(value, dict):
        for key, nested in value.items():
            key_norm = str(key or "").strip().lower()
            if key_norm in _FORBIDDEN_KEYS or any(part in key_norm for part in ("password", "token", "phone", "email")):
                raise AnalyticsError("payload_contains_forbidden_fields")
            reject_forbidden_payload(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            reject_forbidden_payload(nested, path=f"{path}[{idx}]")


class AnalyticsSinkPort(Protocol):
    def write(self, envelope: dict[str, Any]) -> bool: ...


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


class PostgresAnalyticsSink:
    """Durable idempotent sink backed by analytics_event_log."""

    def write(self, envelope: dict[str, Any]) -> bool:
        event_id = str(envelope.get("event_id") or "").strip()
        if not event_id:
            raise AnalyticsError("event_id_required")
        if not postgres_utils.use_postgres():
            raise AnalyticsError("postgres_sink_unavailable")
        postgres_utils.init_schema()
        scope = envelope.get("scope") or {}
        try:
            from psycopg.types.json import Jsonb
        except Exception as exc:  # pragma: no cover
            raise AnalyticsError("psycopg_required") from exc
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM analytics_event_log WHERE event_id = %s", (event_id,))
            if cur.fetchone():
                return False
            cur.execute(
                """
                INSERT INTO analytics_event_log (
                    event_id, schema_version, event_type, occurred_at, received_at,
                    tenant_id, store_id, session_ref, order_ref, member_opaque_ref,
                    payload, source, published_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, NOW()
                )
                """,
                (
                    event_id,
                    str(envelope.get("schema_version") or "analytics-v1"),
                    str(envelope.get("type") or ""),
                    envelope.get("occurred_at") or _now(),
                    envelope.get("received_at") or _now(),
                    UUID(str(scope.get("tenant_id"))),
                    UUID(str(scope["store_id"])) if scope.get("store_id") else None,
                    str(envelope.get("session_ref") or ""),
                    str(envelope.get("order_ref") or ""),
                    str(envelope.get("member_ref") or ""),
                    Jsonb(dict(envelope.get("payload") or {})),
                    str(envelope.get("source") or ""),
                ),
            )
            if str(envelope.get("schema_version") or "") == "commercial-touch-v1":
                payload = dict(envelope.get("payload") or {})
                decision_id = str(payload.get("decision_id") or "")
                if decision_id:
                    cur.execute("SELECT 1 FROM recommendation_decisions WHERE decision_id = %s", (decision_id,))
                    if cur.fetchone() is None:
                        decision_id = ""
                event_type = str(envelope.get("type") or "").removeprefix("commercial_touch.")
                cur.execute(
                    """
                    INSERT INTO commercial_touch_events (
                        event_id, tenant_id, store_id, device_id, decision_id,
                        impression_id, event_type, placement, campaign_id,
                        campaign_version, item_id, session_ref, data_quality,
                        payload, occurred_at, received_at
                    ) VALUES (
                        %s, %s, %s, NULLIF(%s, '')::uuid, NULLIF(%s, ''),
                        NULLIF(%s, ''), %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s
                    ) ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        event_id, UUID(str(scope.get("tenant_id"))), UUID(str(scope["store_id"])),
                        str(payload.get("device_id") or ""), decision_id,
                        str(payload.get("impression_id") or ""), event_type,
                        str(payload.get("placement") or ""), str(payload.get("campaign_id") or ""),
                        int(payload["campaign_version"]) if str(payload.get("campaign_version") or "").isdigit() else None,
                        str(payload.get("item_id") or ""), str(envelope.get("session_ref") or ""),
                        str(payload.get("data_quality") or "complete"), Jsonb(payload),
                        envelope.get("occurred_at") or _now(), envelope.get("received_at") or _now(),
                    ),
                )
            conn.commit()
        return True


def default_sink() -> AnalyticsSinkPort:
    if postgres_utils.use_postgres():
        return PostgresAnalyticsSink()
    return InMemoryAnalyticsSink()


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
    reject_forbidden_payload(payload or {})
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


def publish(envelope: dict[str, Any], *, sink: AnalyticsSinkPort | None = None) -> bool:
    reject_forbidden_payload((envelope or {}).get("payload") or {})
    active = sink or default_sink()
    accepted = active.write(envelope)
    # JSON compatibility mirror for non-postgres or dual observability.
    if accepted and not isinstance(active, PostgresAnalyticsSink):
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
        existing.append(envelope)
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return accepted


def _load_source_rows() -> list[dict[str, Any]]:
    if postgres_utils.use_postgres():
        postgres_utils.init_schema()
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_id, schema_version, event_type AS type, occurred_at, received_at,
                       tenant_id, store_id, session_ref, order_ref, member_opaque_ref AS member_ref,
                       payload, source
                FROM analytics_event_log
                ORDER BY occurred_at ASC
                """
            )
            rows: list[dict[str, Any]] = []
            for row in cur.fetchall():
                item = dict(row)
                item["scope"] = {
                    "tenant_id": str(item.pop("tenant_id")),
                    "store_id": str(item["store_id"]) if item.get("store_id") else None,
                }
                item.pop("store_id", None)
                if hasattr(item.get("occurred_at"), "isoformat"):
                    item["occurred_at"] = item["occurred_at"].isoformat()
                if hasattr(item.get("received_at"), "isoformat"):
                    item["received_at"] = item["received_at"].isoformat()
                rows.append(item)
            return rows
    path = _path()
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return rows if isinstance(rows, list) else []


def list_events(*, tenant_id: UUID, store_id: UUID, since: str = "", until: str = "") -> list[dict[str, Any]]:
    """Read immutable analytics facts within one commercial scope."""

    rows = _load_source_rows()
    return [
        row for row in rows
        if (row.get("scope") or {}).get("tenant_id") == str(tenant_id)
        and (row.get("scope") or {}).get("store_id") == str(store_id)
        and (not since or str(row.get("occurred_at") or "") >= since)
        and (not until or str(row.get("occurred_at") or "") <= until)
    ]


def replay(
    *,
    event_type: str | None = None,
    tenant_id: UUID | None = None,
    since: str | None = None,
    sink: AnalyticsSinkPort | None = None,
) -> int:
    rows = _load_source_rows()
    active = sink or InMemoryAnalyticsSink()
    count = 0
    last_event_id = ""
    for row in rows:
        if event_type and row.get("type") != event_type:
            continue
        if tenant_id and (row.get("scope") or {}).get("tenant_id") != str(tenant_id):
            continue
        if since and str(row.get("occurred_at") or "") < since:
            continue
        if active.write(row):
            count += 1
            last_event_id = str(row.get("event_id") or last_event_id)
    checkpoint = {
        "replayed_at": _now(),
        "count": count,
        "event_type": event_type,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "since": since,
        "last_event_id": last_event_id,
    }
    cp = _checkpoints_path()
    cp.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if postgres_utils.use_postgres():
        try:
            postgres_utils.init_schema()
            with postgres_utils.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analytics_checkpoints (checkpoint_id, tenant_id, event_type, last_event_id, last_occurred_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (checkpoint_id) DO UPDATE SET
                        last_event_id = EXCLUDED.last_event_id,
                        last_occurred_at = NOW(),
                        updated_at = NOW()
                    """,
                    (
                        f"replay:{event_type or 'all'}:{tenant_id or 'all'}",
                        tenant_id,
                        event_type or "",
                        last_event_id,
                    ),
                )
                conn.commit()
        except Exception:
            pass
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
