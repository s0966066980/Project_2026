"""Secure kiosk fleet heartbeat, config versioning, rollout rings, and commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import config

ALLOWED_COMMANDS = frozenset({"refresh_config", "restart_app", "collect_safe_diagnostics", "update"})
ROLLOUT_RINGS = ("internal", "pilot", "percentage", "general")


class FleetError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "fleet_devices.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"devices": {}, "commands": [], "configs": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"devices": {}, "commands": [], "configs": {}}
    if not isinstance(data, dict):
        return {"devices": {}, "commands": [], "configs": {}}
    data.setdefault("devices", {})
    data.setdefault("commands", [])
    data.setdefault("configs", {})
    return data


def _save(data: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def heartbeat(
    *,
    device_id: UUID,
    tenant_id: UUID,
    store_id: UUID,
    app_version: str,
    config_version: str,
    health: str = "ok",
    last_error: str = "",
) -> dict[str, Any]:
    data = _load()
    key = str(device_id)
    data["devices"][key] = {
        "device_id": key,
        "tenant_id": str(tenant_id),
        "store_id": str(store_id),
        "online": True,
        "last_seen": _now(),
        "app_version": app_version,
        "config_version": config_version,
        "health": health,
        "last_error": str(last_error or "")[:200],
        "deployment_ring": data.get("devices", {}).get(key, {}).get("deployment_ring", "pilot"),
    }
    _save(data)
    # Durable last-known state when PostgreSQL is configured.
    try:
        from repositories import postgres_utils

        if postgres_utils.use_postgres():
            with postgres_utils.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO fleet_device_state (
                        device_id, tenant_id, store_id, app_version, config_version,
                        health, last_error, deployment_ring, last_seen_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (device_id) DO UPDATE SET
                        app_version = EXCLUDED.app_version,
                        config_version = EXCLUDED.config_version,
                        health = EXCLUDED.health,
                        last_error = EXCLUDED.last_error,
                        last_seen_at = NOW(),
                        updated_at = NOW()
                    """,
                    (
                        device_id,
                        tenant_id,
                        store_id,
                        app_version,
                        config_version,
                        health,
                        str(last_error or "")[:200],
                        data["devices"][key]["deployment_ring"],
                    ),
                )
                conn.commit()
    except Exception:
        # JSON path remains operational; durable write is best-effort until scope rows exist.
        pass
    # Ephemeral presence via Redis when available (not source of truth).
    try:
        from services import shared_infrastructure_service

        cache = getattr(shared_infrastructure_service, "cache", None)
        if cache is not None:
            cache().set(
                f"fleet:presence:{tenant_id}:{device_id}",
                "1",
                ttl_seconds=60,
            )
    except Exception:
        pass
    return data["devices"][key]


def set_ring(device_id: UUID, ring: str) -> dict[str, Any]:
    if ring not in ROLLOUT_RINGS:
        raise FleetError("invalid_rollout_ring")
    data = _load()
    key = str(device_id)
    device = data["devices"].get(key)
    if device is None:
        raise FleetError("device_not_found")
    device["deployment_ring"] = ring
    _save(data)
    return device


def publish_config(
    *,
    tenant_id: UUID,
    store_id: UUID | None,
    version: str,
    payload: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    data = _load()
    record = {
        "version": version,
        "tenant_id": str(tenant_id),
        "store_id": str(store_id) if store_id else None,
        "payload": payload,
        "actor": actor,
        "published_at": _now(),
    }
    data["configs"][version] = record
    _save(data)
    return record


def issue_command(
    *,
    device_id: UUID,
    tenant_id: UUID,
    command: str,
    actor: str,
    expires_at: str,
    command_id: str | None = None,
) -> dict[str, Any]:
    if command not in ALLOWED_COMMANDS:
        raise FleetError("command_not_allowlisted")
    data = _load()
    device = data["devices"].get(str(device_id))
    if device is None:
        raise FleetError("device_not_found")
    if device.get("tenant_id") != str(tenant_id):
        raise FleetError("scope_mismatch")
    cid = command_id or f"cmd_{uuid4().hex[:12]}"
    # Idempotent by command_id
    for row in data["commands"]:
        if row.get("command_id") == cid:
            return row
    row = {
        "command_id": cid,
        "device_id": str(device_id),
        "tenant_id": str(tenant_id),
        "command": command,
        "actor": actor,
        "issued_at": _now(),
        "expires_at": expires_at,
        "status": "pending",
    }
    data["commands"].append(row)
    _save(data)
    return row


def consume_command(command_id: str, *, now: str | None = None) -> dict[str, Any] | None:
    data = _load()
    clock = now or _now()
    for row in data["commands"]:
        if row.get("command_id") != command_id:
            continue
        if row.get("status") != "pending":
            return row
        if str(row.get("expires_at") or "") and str(row["expires_at"]) < clock:
            row["status"] = "expired"
            _save(data)
            raise FleetError("command_expired")
        row["status"] = "applied"
        row["applied_at"] = clock
        _save(data)
        return row
    return None
