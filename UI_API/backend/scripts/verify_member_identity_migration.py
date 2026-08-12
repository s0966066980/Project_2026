"""Backfill and verify Member UUID/PII migration without emitting PII."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence, TypedDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from modules.member._pii import configured_key_provider, phone_lookup_hash, protect_phone  # noqa: E402
from repositories import postgres_utils  # noqa: E402
from services.member_key_provider import MemberKeyProvider  # noqa: E402


class Violation(TypedDict):
    type: str
    count: int


def backfill_member_identity(provider: MemberKeyProvider) -> int:
    """Idempotently protect compatibility values using the active key version."""

    updated = 0
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, phone AS compatibility_value, key_version
            FROM members
            WHERE anonymized_at IS NULL
              AND (phone_lookup_hash IS NULL OR phone_encrypted IS NULL OR key_version IS DISTINCT FROM %s)
            ORDER BY id
            FOR UPDATE
            """,
            (provider.active_version,),
        )
        for row in cur.fetchall():
            protected = protect_phone(row["compatibility_value"], row["tenant_id"], provider)
            cur.execute(
                """
                UPDATE members
                SET phone_lookup_hash = %s,
                    phone_encrypted = %s,
                    phone_masked = %s,
                    key_version = %s,
                    pii_updated_at = NOW()
                WHERE id = %s AND tenant_id = %s
                """,
                (
                    protected.phone_lookup_hash,
                    protected.phone_encrypted,
                    protected.phone_masked,
                    protected.key_version,
                    row["id"],
                    row["tenant_id"],
                ),
            )
            updated += int(cur.rowcount)
        conn.commit()
    return updated


def _count(cur, query: str) -> int:
    cur.execute(query)
    return int((cur.fetchone() or {}).get("count") or 0)


def collect_violations(provider: MemberKeyProvider) -> list[Violation]:
    checks = {
        "missing_member_id": """
            SELECT COUNT(*) AS count FROM members
            WHERE id IS NULL OR (
                anonymized_at IS NULL AND (
                    phone_lookup_hash IS NULL OR phone_encrypted IS NULL OR key_version IS NULL
                )
            )
        """,
        "duplicate_lookup_hash": """
            SELECT COUNT(*) AS count FROM (
                SELECT tenant_id, phone_lookup_hash FROM members
                WHERE phone_lookup_hash IS NOT NULL
                GROUP BY tenant_id, phone_lookup_hash HAVING COUNT(*) > 1
            ) duplicates
        """,
        "reference_mismatch": """
            SELECT (
                (SELECT COUNT(*) FROM member_preferences child JOIN members parent ON parent.id = child.member_id
                 WHERE child.tenant_id <> parent.tenant_id) +
                (SELECT COUNT(*) FROM member_sessions child JOIN members parent ON parent.id = child.member_id
                 WHERE child.tenant_id <> parent.tenant_id) +
                (SELECT COUNT(*) FROM member_orders child JOIN members parent ON parent.id = child.member_id
                 WHERE child.tenant_id <> parent.tenant_id)
            ) AS count
        """,
        "orphan_member_reference": """
            SELECT (
                (SELECT COUNT(*) FROM member_preferences child WHERE NOT EXISTS
                    (SELECT 1 FROM members parent WHERE parent.id = child.member_id)) +
                (SELECT COUNT(*) FROM member_sessions child WHERE NOT EXISTS
                    (SELECT 1 FROM members parent WHERE parent.id = child.member_id)) +
                (SELECT COUNT(*) FROM member_orders child WHERE NOT EXISTS
                    (SELECT 1 FROM members parent WHERE parent.id = child.member_id))
            ) AS count
        """,
    }
    violations: list[Violation] = []
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        for violation_type, query in checks.items():
            count = _count(cur, query)
            if count:
                violations.append({"type": violation_type, "count": count})
        cur.execute(
            """
            SELECT tenant_id, phone AS compatibility_value, phone_lookup_hash
            FROM members WHERE phone_lookup_hash IS NOT NULL AND anonymized_at IS NULL
            """
        )
        drift = sum(
            1
            for row in cur.fetchall()
            if phone_lookup_hash(row["compatibility_value"], row["tenant_id"], provider) != row["phone_lookup_hash"]
        )
    if drift:
        violations.append({"type": "dual_write_drift", "count": drift})
    return violations


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill or verify Member UUID/PII migration.")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        provider = configured_key_provider()
        updated = backfill_member_identity(provider) if args.backfill else 0
        violations = collect_violations(provider)
        payload = {"valid": not violations, "updated_count": updated, "violations": violations}
        print(json.dumps(payload, sort_keys=True))
        return 1 if args.require_clean and violations else 0
    except (postgres_utils.PostgresUnavailableError, RuntimeError):
        print(
            json.dumps(
                {
                    "valid": False,
                    "updated_count": 0,
                    "violations": [{"type": "verification_unavailable", "count": 1}],
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
