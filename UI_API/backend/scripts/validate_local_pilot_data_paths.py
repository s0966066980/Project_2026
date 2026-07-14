#!/usr/bin/env python3
"""Validate local-pilot commercial data stays on PostgreSQL (no JSON SoT)."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

COMMERCIAL_REPO_FILES = (
    "repositories/member_repository.py",
    "repositories/checkout_order_repository.py",
    "repositories/admin_identity_repository.py",
    "repositories/device_identity_repository.py",
    "repositories/worker_job_repository.py",
    "modules/identity/adapters/postgres.py",
)


def _is_local_pilot() -> bool:
    return (
        os.getenv("APP_PROFILE", "").strip().lower() == "local-pilot"
        or (
            os.getenv("APP_ENV", "").strip().lower() == "production"
            and os.getenv("MEMBER_STORAGE_BACKEND", "").strip().lower() == "postgres"
            and os.getenv("SECURITY_ENFORCED", "").strip().lower() in {"1", "true", "yes", "on"}
        )
    )


def main() -> int:
    fails = 0
    warns = 0

    def pass_(m: str) -> None:
        print(f"PASS: {m}")

    def warn(m: str) -> None:
        nonlocal warns
        warns += 1
        print(f"WARN: {m}")

    def fail(m: str) -> None:
        nonlocal fails
        fails += 1
        print(f"FAIL: {m}")

    profile = os.getenv("APP_PROFILE", "")
    print(f"INFO: APP_PROFILE={profile or '(unset)'}")
    if not _is_local_pilot():
        warn("not in local-pilot mode; running structural checks only")

    backend = os.getenv("MEMBER_STORAGE_BACKEND", "json").strip().lower()
    if _is_local_pilot() and backend != "postgres":
        fail("local-pilot requires MEMBER_STORAGE_BACKEND=postgres")
    else:
        pass_("storage backend check")

    if _is_local_pilot() and os.getenv("ALLOW_POSTGRES_JSON_FALLBACK", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        fail("local-pilot must not allow postgres JSON fallback")
    else:
        pass_("no JSON fallback flag for pilot")

    # Structural: commercial adapters must not open learning_data json paths as SoT
    for rel in COMMERCIAL_REPO_FILES:
        path = BACKEND / rel
        if not path.is_file():
            warn(f"missing expected file {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "learning_data" in text and "json" in text.lower() and "use_postgres" not in text:
            fail(f"{rel} appears to use learning_data JSON without postgres gate")
        else:
            pass_(f"{rel} present")

    print(f"summary: fail={fails} warn={warns}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
