"""Validate aggregate commercial scope integrity without exposing business data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from repositories import postgres_utils  # noqa: E402
from services.commercial_scope_readiness_service import (  # noqa: E402
    CommercialScopeReadinessError,
    validate_configured_commercial_scope,
)

Violation = tuple[str, str, int]


def _count(cur, table: str, violation_type: str, predicate: str) -> Violation | None:
    cur.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}")
    count = int((cur.fetchone() or {}).get("count") or 0)
    return (table, violation_type, count) if count else None


def collect_violations() -> list[Violation]:
    """Return only table, violation type, and count for scope integrity failures."""

    checks = (
        ("members", "missing_tenant_scope", "tenant_id IS NULL"),
        (
            "members",
            "orphan_tenant_scope",
            "tenant_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tenants WHERE tenants.id = members.tenant_id)",
        ),
        ("member_sessions", "missing_tenant_scope", "tenant_id IS NULL"),
        ("member_sessions", "missing_store_scope", "store_id IS NULL"),
        ("member_sessions", "missing_device_scope", "origin_device_id IS NULL"),
        (
            "member_sessions",
            "orphan_or_mismatched_scope",
            "tenant_id IS NOT NULL AND store_id IS NOT NULL AND origin_device_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM devices WHERE devices.id = member_sessions.origin_device_id AND devices.store_id = member_sessions.store_id AND devices.tenant_id = member_sessions.tenant_id)",
        ),
        ("member_orders", "missing_tenant_scope", "tenant_id IS NULL"),
        ("member_orders", "missing_store_scope", "store_id IS NULL"),
        ("member_orders", "missing_device_scope", "origin_device_id IS NULL"),
        (
            "member_orders",
            "orphan_or_mismatched_scope",
            "tenant_id IS NOT NULL AND store_id IS NOT NULL AND origin_device_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM devices WHERE devices.id = member_orders.origin_device_id AND devices.store_id = member_orders.store_id AND devices.tenant_id = member_orders.tenant_id)",
        ),
        ("recommendation_events", "missing_tenant_scope", "tenant_id IS NULL"),
        ("recommendation_events", "missing_store_scope", "store_id IS NULL"),
        ("recommendation_events", "missing_device_scope", "device_id IS NULL"),
        (
            "recommendation_events",
            "orphan_or_mismatched_scope",
            "tenant_id IS NOT NULL AND store_id IS NOT NULL AND device_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM devices WHERE devices.id = recommendation_events.device_id AND devices.store_id = recommendation_events.store_id AND devices.tenant_id = recommendation_events.tenant_id)",
        ),
        ("admin_audit_logs", "missing_tenant_scope", "tenant_id IS NULL"),
        (
            "admin_audit_logs",
            "orphan_store_scope",
            "store_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM stores WHERE stores.id = admin_audit_logs.store_id AND stores.tenant_id = admin_audit_logs.tenant_id)",
        ),
        (
            "devices",
            "hierarchy_mismatch",
            "NOT EXISTS (SELECT 1 FROM stores WHERE stores.id = devices.store_id AND stores.tenant_id = devices.tenant_id)",
        ),
        (
            "store_availability",
            "orphan_or_mismatched_scope",
            "NOT EXISTS (SELECT 1 FROM stores WHERE stores.id = store_availability.store_id AND stores.tenant_id = store_availability.tenant_id)",
        ),
        ("commercial_settings_versions", "missing_tenant_scope", "tenant_id IS NULL"),
        (
            "commercial_settings_versions",
            "orphan_store_scope",
            "store_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM stores WHERE stores.id = commercial_settings_versions.store_id AND stores.tenant_id = commercial_settings_versions.tenant_id)",
        ),
        (
            "promotion_records",
            "orphan_or_mismatched_scope",
            "NOT EXISTS (SELECT 1 FROM stores WHERE stores.id = promotion_records.store_id AND stores.tenant_id = promotion_records.tenant_id)",
        ),
        (
            "interaction_events",
            "orphan_or_mismatched_scope",
            "NOT EXISTS (SELECT 1 FROM devices WHERE devices.id = interaction_events.device_id AND devices.store_id = interaction_events.store_id AND devices.tenant_id = interaction_events.tenant_id)",
        ),
        (
            "intervention_outcomes",
            "orphan_or_mismatched_scope",
            "NOT EXISTS (SELECT 1 FROM devices WHERE devices.id = intervention_outcomes.device_id AND devices.store_id = intervention_outcomes.store_id AND devices.tenant_id = intervention_outcomes.tenant_id)",
        ),
        ("rag_asset_scopes", "missing_tenant_scope", "tenant_id IS NULL"),
        (
            "rag_asset_scopes",
            "orphan_store_scope",
            "store_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM stores WHERE stores.id = rag_asset_scopes.store_id AND stores.tenant_id = rag_asset_scopes.tenant_id)",
        ),
    )
    violations: list[Violation] = []
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            for table, violation_type, predicate in checks:
                result = _count(cur, table, violation_type, predicate)
                if result:
                    violations.append(result)
    try:
        validate_configured_commercial_scope()
    except CommercialScopeReadinessError:
        violations.append(("configured_scope", "not_ready", 1))
    return violations


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate aggregate commercial scope integrity.")
    parser.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        violations = collect_violations()
        payload = {
            "valid": not violations,
            "violations": [
                {"table": table, "type": violation_type, "count": count} for table, violation_type, count in violations
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1 if args.require_complete and violations else 0
    except postgres_utils.PostgresUnavailableError:
        print(json.dumps({"valid": False, "violations": [{"table": "database", "type": "unavailable", "count": 1}]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
