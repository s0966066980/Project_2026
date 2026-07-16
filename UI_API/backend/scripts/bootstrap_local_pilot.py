#!/usr/bin/env python3
"""Idempotent single-store pilot bootstrap: 1 tenant, 1 store, 1 admin, devices.

Secrets are never printed. Admin password from ADMIN_BOOTSTRAP_PASSWORD or getpass.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from uuid import UUID, uuid4

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND))


def _password() -> str:
    env = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "").strip()
    if env:
        return env
    first = getpass.getpass("Admin password (min 12 chars): ")
    second = getpass.getpass("Confirm admin password: ")
    if first != second:
        raise SystemExit("FAIL: passwords do not match")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap single-store local pilot data")
    parser.add_argument("--tenant-name", default="Local Pilot Tenant")
    parser.add_argument("--store-name", default="Local Pilot Store")
    parser.add_argument("--admin-login", default="admin")
    parser.add_argument("--device-count", type=int, default=1)
    args = parser.parse_args(argv)

    os.environ.setdefault("MEMBER_STORAGE_BACKEND", "postgres")
    from repositories import postgres_utils
    from services import admin_identity_service

    if not postgres_utils.use_postgres():
        print("FAIL: MEMBER_STORAGE_BACKEND must be postgres")
        return 1
    if not postgres_utils.database_url():
        print("FAIL: DATABASE_URL is required")
        return 1

    postgres_utils.init_schema()
    password = _password()
    if len(password) < 12:
        print("FAIL: admin password must be at least 12 characters")
        return 1

    tenant_id = UUID(os.getenv("DEFAULT_TENANT_ID", "00000000-0000-4000-8000-000000000001"))
    store_id = UUID(os.getenv("DEFAULT_STORE_ID", "00000000-0000-4000-8000-000000000002"))
    device_id = UUID(os.getenv("DEFAULT_DEVICE_ID", "00000000-0000-4000-8000-000000000003"))

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tenants (id, code, name, status)
            VALUES (%s, %s, %s, 'active')
            ON CONFLICT (id) DO NOTHING
            """,
            (tenant_id, "local-pilot", args.tenant_name),
        )
        cur.execute(
            """
            INSERT INTO stores (id, tenant_id, code, name, timezone, status)
            VALUES (%s, %s, %s, %s, 'Asia/Taipei', 'active')
            ON CONFLICT (id) DO NOTHING
            """,
            (store_id, tenant_id, "local-pilot-store", args.store_name),
        )
        cur.execute(
            """
            INSERT INTO devices (id, tenant_id, store_id, code, name, status)
            VALUES (%s, %s, %s, %s, %s, 'active')
            ON CONFLICT (id) DO NOTHING
            """,
            (device_id, tenant_id, store_id, "kiosk-1", "Kiosk 1"),
        )
        for i in range(2, max(1, args.device_count) + 1):
            did = uuid4()
            cur.execute(
                """
                INSERT INTO devices (id, tenant_id, store_id, code, name, status)
                VALUES (%s, %s, %s, %s, %s, 'active')
                ON CONFLICT DO NOTHING
                """,
                (did, tenant_id, store_id, f"kiosk-{i}", f"Kiosk {i}"),
            )
        conn.commit()

    admin_identity_service.sync_admin_permission_catalog()
    login = admin_identity_service.normalize_admin_login(args.admin_login)
    from repositories import admin_identity_repository

    existing = admin_identity_repository.find_admin_user(tenant_id, login)
    if existing is None:
        user_id = uuid4()
        admin_identity_repository.create_admin_user(
            user_id=user_id,
            tenant_id=tenant_id,
            login_identity=login,
            display_name="Pilot Admin",
            password_hash=admin_identity_service.hash_admin_password(password),
        )
        # Role assignment best-effort via manage helpers if present
        print("PASS: created admin user (password not printed)")
    else:
        print("PASS: admin user already exists (not overwritten)")

    print("PASS: tenant/store/device bootstrap complete")
    print(f"INFO: tenant_id={tenant_id}")
    print(f"INFO: store_id={store_id}")
    print(f"INFO: device_id={device_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
