"""Versioned Campaign persistence adapter with PostgreSQL and local JSON paths."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import config
from models.commercial_scope import CommercialScope, is_legacy_store_scope
from modules.operations.adapters import audit as admin_audit_repository
from modules.promotion.adapters import promotion as promotion_repository
from modules.promotion.contracts import CampaignConflictError, CampaignSnapshot
from repositories import postgres_utils

_lock = threading.Lock()


def _path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "campaign_versions.json"


def _read_rows() -> list[dict]:
    try:
        rows = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _write_rows(rows: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".json.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class CampaignRepository:
    def get(self, scope: CommercialScope, campaign_id: str) -> CampaignSnapshot | None:
        if postgres_utils.use_postgres():
            with postgres_utils.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT d.campaign_id, d.current_version, d.status, v.payload
                       FROM campaign_definitions d
                       JOIN campaign_versions v ON v.campaign_definition_id = d.id AND v.version = d.current_version
                       WHERE d.tenant_id = %s AND d.store_id = %s AND d.campaign_id = %s""",
                    (scope.tenant_id, scope.store_id, campaign_id),
                )
                row = cur.fetchone()
            return (
                CampaignSnapshot(
                    str(row["campaign_id"]), int(row["current_version"]), str(row["status"]), dict(row["payload"])
                )
                if row
                else None
            )
        if not is_legacy_store_scope(scope):
            return None
        matches = [row for row in _read_rows() if row.get("campaign_id") == campaign_id]
        if not matches:
            return None
        row = max(matches, key=lambda item: int(item.get("version") or 0))
        return CampaignSnapshot(campaign_id, int(row["version"]), str(row["status"]), dict(row.get("payload") or {}))

    def list(self, scope: CommercialScope) -> list[CampaignSnapshot]:
        if postgres_utils.use_postgres():
            with postgres_utils.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT d.campaign_id, d.current_version, d.status, v.payload
                       FROM campaign_definitions d
                       JOIN campaign_versions v ON v.campaign_definition_id = d.id AND v.version = d.current_version
                       WHERE d.tenant_id = %s AND d.store_id = %s
                       ORDER BY d.updated_at DESC""",
                    (scope.tenant_id, scope.store_id),
                )
                return [
                    CampaignSnapshot(
                        str(row["campaign_id"]), int(row["current_version"]), str(row["status"]), dict(row["payload"])
                    )
                    for row in cur.fetchall()
                ]
        if not is_legacy_store_scope(scope):
            return []
        latest: dict[str, dict] = {}
        for row in _read_rows():
            key = str(row.get("campaign_id") or "")
            if key and int(row.get("version") or 0) > int(latest.get(key, {}).get("version") or 0):
                latest[key] = row
        return [
            CampaignSnapshot(key, int(row["version"]), str(row["status"]), dict(row.get("payload") or {}))
            for key, row in latest.items()
        ]

    def append_version(
        self,
        scope: CommercialScope,
        campaign_id: str,
        payload: dict,
        status: str,
        *,
        expected_version: int,
        actor_id: str,
    ) -> CampaignSnapshot:
        if postgres_utils.use_postgres():
            from psycopg.types.json import Jsonb

            with postgres_utils.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT id, current_version FROM campaign_definitions
                       WHERE tenant_id = %s AND store_id = %s AND campaign_id = %s FOR UPDATE""",
                    (scope.tenant_id, scope.store_id, campaign_id),
                )
                definition = cur.fetchone()
                current = int(definition["current_version"]) if definition else 0
                if current != expected_version:
                    raise CampaignConflictError("campaign_version_conflict")
                definition_id = definition["id"] if definition else uuid4()
                next_version = current + 1
                if not definition:
                    cur.execute(
                        """INSERT INTO campaign_definitions
                           (id, campaign_id, tenant_id, store_id, current_version, status)
                           VALUES (%s, %s, %s, %s, 0, %s)""",
                        (definition_id, campaign_id, scope.tenant_id, scope.store_id, status),
                    )
                cur.execute(
                    """INSERT INTO campaign_versions
                       (id, campaign_definition_id, version, status, payload, actor_id, published_at)
                       VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s IN ('scheduled','active') THEN NOW() END)""",
                    (uuid4(), definition_id, next_version, status, Jsonb(payload), actor_id, status),
                )
                cur.execute(
                    """UPDATE campaign_definitions SET current_version = %s, status = %s, updated_at = NOW()
                       WHERE id = %s AND current_version = %s""",
                    (next_version, status, definition_id, current),
                )
                if cur.rowcount != 1:
                    raise CampaignConflictError("campaign_version_conflict")
                conn.commit()
            return CampaignSnapshot(campaign_id, next_version, status, dict(payload))
        if not is_legacy_store_scope(scope):
            raise ValueError("JSON campaign storage only supports the legacy Default Scope")
        with _lock:
            rows = _read_rows()
            current = max(
                (int(row.get("version") or 0) for row in rows if row.get("campaign_id") == campaign_id), default=0
            )
            if current != expected_version:
                raise CampaignConflictError("campaign_version_conflict")
            next_version = current + 1
            rows.append(
                {
                    "campaign_id": campaign_id,
                    "version": next_version,
                    "status": status,
                    "payload": payload,
                    "actor_id": actor_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _write_rows(rows)
        return CampaignSnapshot(campaign_id, next_version, status, dict(payload))

    def project_legacy(self, scope: CommercialScope, snapshot: CampaignSnapshot) -> None:
        payload = dict(snapshot.payload)
        rules = payload.get("promotion_rules") or []
        rule = dict(rules[0]) if rules else {}
        placements = list(payload.get("placements") or [])
        creative = dict(payload.get("creatives") or {})
        record = {
            "id": snapshot.campaign_id,
            "offer_id": snapshot.campaign_id,
            "title": payload.get("name") or snapshot.campaign_id,
            "status": "active" if snapshot.status in {"active", "scheduled"} else "inactive",
            "enabled": snapshot.status in {"active", "scheduled"},
            "placements": placements,
            "surface": placements[0] if placements else "recommendation",
            "start_at": (payload.get("schedule") or {}).get("starts_at", ""),
            "end_at": (payload.get("schedule") or {}).get("ends_at", ""),
            "timezone": "Asia/Taipei",
            "member_only": payload.get("audience") == "member",
            "item_ids": rule.get("item_ids") or [],
            "required_cart_item_ids": rule.get("required_cart_item_ids") or [],
            "promo_price": rule.get("promotion_price"),
            "pricing": {"type": rule.get("type"), "promotion_price": rule.get("promotion_price"), "currency": "TWD"},
            "badge": creative.get("badge", ""),
            "subtitle": creative.get("description", ""),
            "cta_text": creative.get("cta", "立即查看"),
            "campaign_version": snapshot.version,
        }
        promotion_repository.save_promotion_scoped(snapshot.campaign_id, record, scope)

    def audit(self, scope: CommercialScope, *, actor_id: str, action: str, snapshot: CampaignSnapshot) -> None:
        admin_audit_repository.append_admin_audit_scoped(
            {
                "audit_id": f"aud_{uuid4().hex}",
                "actor": actor_id,
                "action": action,
                "target_type": "campaign",
                "target_id": snapshot.campaign_id,
                "metadata": {"version": snapshot.version, "status": snapshot.status},
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            scope,
        )


default_campaign_repository = CampaignRepository()
