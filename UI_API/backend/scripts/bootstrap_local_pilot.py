#!/usr/bin/env python3
"""Idempotent single-store pilot bootstrap: scope, Admin RBAC, and device credential.

Secrets are never printed. Admin password comes from trusted input and the device
credential is written once to a repository-external file with mode 0600.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT_DIR.parent
BACKEND = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND))

DEFAULT_DEVICE_BUNDLE = Path.home() / ".config/project-2026/secrets/device-1-provisioning.json"
DEFAULT_ADMIN_BUNDLE = Path.home() / ".config/project-2026/secrets/admin-login.json"
DEFAULT_PILOT_ENV = Path.home() / ".config/project-2026/local-pilot.env"


def _password() -> str:
    env = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "").strip()
    if env:
        return env
    first = getpass.getpass("Admin password (min 12 chars): ")
    second = getpass.getpass("Confirm admin password: ")
    if first != second:
        raise SystemExit("FAIL: passwords do not match")
    return first


def _external_secret_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path.is_relative_to(REPOSITORY_ROOT.resolve()):
        raise ValueError("device credential output must be outside the repository")
    return path


def _write_private_text(path: Path, text: str) -> None:
    """Create a private file exactly once without a world-readable intermediate file."""
    destination = _external_secret_path(path)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        destination.chmod(0o600)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _replace_private_text(path: Path, text: str) -> None:
    destination = _external_secret_path(path)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    _write_private_text(temporary, text)
    try:
        os.replace(temporary, destination)
        destination.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _write_secret_bundle(path: Path, payload: dict[str, object]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    _write_private_text(path, serialized)


def _write_pilot_environment(
    *,
    output_path: Path,
    tenant_id: UUID,
    store_id: UUID,
    device_id: UUID,
    admin_login: str,
) -> None:
    destination = _external_secret_path(output_path)
    if destination.exists():
        if destination.stat().st_mode & 0o077:
            raise RuntimeError(f"existing Pilot environment file is not private: {destination}")
        lines = destination.read_text(encoding="utf-8").splitlines()
        synchronized: list[str] = []
        ngrok_seen = False
        for line in lines:
            if line.startswith("ENABLE_NGROK="):
                synchronized.append("ENABLE_NGROK=false")
                ngrok_seen = True
            else:
                synchronized.append(line)
        if not ngrok_seen:
            synchronized.append("ENABLE_NGROK=false")
        _replace_private_text(destination, "\n".join(synchronized) + "\n")
        print(f"PASS: existing private Pilot environment safety keys synchronized at {destination}")
        return
    database_url_file = str(os.getenv("DATABASE_URL_FILE", "") or "").strip()
    migration_url_file = str(os.getenv("MIGRATION_DATABASE_URL_FILE", "") or "").strip()
    if not database_url_file or not Path(database_url_file).is_file():
        raise RuntimeError("DATABASE_URL_FILE is required to create a secret-free Pilot environment")
    if not migration_url_file or not Path(migration_url_file).is_file():
        raise RuntimeError("MIGRATION_DATABASE_URL_FILE is required to create the Pilot environment")
    values = {
        "APP_PROFILE": "local-pilot",
        "APP_ENV": "pilot",
        "DATABASE_BACKEND": "postgresql",
        "DATABASE_TOPOLOGY": "single",
        "DATABASE_URL_FILE": database_url_file,
        "MIGRATION_DATABASE_URL_FILE": migration_url_file,
        "DATABASE_RUNTIME_ROLE": str(os.getenv("DATABASE_RUNTIME_ROLE", "project_runtime") or "project_runtime"),
        "RUNTIME_DATA_ROOT": str(os.getenv("RUNTIME_DATA_ROOT", Path.home() / ".local/share/project-2026")),
        "SECURITY_ENFORCED": "true",
        "ENABLE_LEGACY_KIOSK_TOKEN": "false",
        "ENABLE_DEMO_ROUTES": "false",
        "ENABLE_DIAGNOSTIC_ROUTES": "false",
        "ENABLE_DEBUG_ROUTES": "false",
        "ALLOW_UNSAFE_PRODUCTION_ROUTES": "false",
        "ENABLE_NGROK": "false",
        "ADMIN_MEMBER_REF_SECRET": secrets.token_urlsafe(48),
        "OBJECT_STORAGE_SIGNING_SECRET": secrets.token_urlsafe(48),
        "DEFAULT_TENANT_ID": str(tenant_id),
        "DEFAULT_STORE_ID": str(store_id),
        "DEFAULT_DEVICE_ID": str(device_id),
        "DEVICE_SESSION_TTL_SEC": "28800",
        "OBJECT_STORAGE_BACKEND": "local",
        "PAYMENT_BACKEND": "manual",
        "POS_BACKEND": "manual",
        "SHARED_RATE_LIMIT_ENABLED": "false",
        "STRUCTURED_LOGGING_ENABLED": "true",
    }
    text = "".join(f"{key}={value}\n" for key, value in values.items())
    _write_private_text(destination, text)
    print(f"PASS: private Pilot environment created at {destination}")


def _generated_admin_password(path: Path, login_identity: str) -> str:
    destination = _external_secret_path(path)
    if destination.exists():
        if destination.stat().st_mode & 0o077:
            raise RuntimeError(f"existing Admin credential bundle is not private: {destination}")
        payload = json.loads(destination.read_text(encoding="utf-8"))
        password = str(payload.get("password", ""))
        if str(payload.get("login_identity", "")) != login_identity or len(password) < 12:
            raise RuntimeError("existing Admin credential bundle is invalid")
        return password
    password = secrets.token_urlsafe(32)
    _write_secret_bundle(
        destination,
        {"version": 1, "login_identity": login_identity, "password": password},
    )
    print(f"PASS: private Admin credential bundle created at {destination}")
    return password


def _ensure_admin_role(tenant_id: UUID, user_id: UUID, permissions: dict[str, UUID]) -> UUID:
    """Idempotently grant the bootstrap Admin the repository permission catalog."""
    from repositories import postgres_utils

    proposed_role_id = uuid4()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_roles (id, tenant_id, code, name, status)
            VALUES (%s, %s, 'bootstrap-admin', 'Bootstrap Administrator', 'active')
            ON CONFLICT (tenant_id, code) DO UPDATE SET
                name = EXCLUDED.name,
                status = 'active',
                updated_at = NOW()
            RETURNING id
            """,
            (proposed_role_id, tenant_id),
        )
        role_id = cur.fetchone()["id"]
        for permission_id in permissions.values():
            cur.execute(
                """
                INSERT INTO admin_role_permissions (tenant_id, role_id, permission_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """,
                (tenant_id, role_id, permission_id),
            )
        cur.execute(
            """
            INSERT INTO admin_user_role_assignments (
                id, tenant_id, user_id, role_id, store_id, status
            ) VALUES (%s, %s, %s, %s, NULL, 'active')
            ON CONFLICT (user_id, role_id) WHERE store_id IS NULL DO UPDATE SET
                status = 'active',
                updated_at = NOW()
            """,
            (uuid4(), tenant_id, user_id, role_id),
        )
        conn.commit()
    return role_id


def _issue_device_bundle(
    *,
    output_path: Path,
    tenant_id: UUID,
    store_id: UUID,
    device_id: UUID,
    admin_user_id: UUID,
) -> None:
    from capabilities.identity_access import device_identity_service
    from models.admin_identity import AdminPrincipal
    from models.commercial_scope import CommercialScope

    destination = _external_secret_path(output_path)
    if destination.exists():
        if destination.stat().st_mode & 0o077:
            raise RuntimeError(f"existing device credential bundle is not private: {destination}")
        print(f"PASS: existing private device credential bundle retained at {destination}")
        return
    principal = AdminPrincipal(
        user_id=admin_user_id,
        tenant_id=tenant_id,
        allowed_store_ids=(store_id,),
        roles=("bootstrap-admin",),
        permissions=("device_identity.manage",),
        session_id=None,
        auth_method="session",
    )
    issued = device_identity_service.issue_device_credential(
        principal,
        CommercialScope(tenant_id, store_id),
        device_id,
    )
    _write_secret_bundle(
        destination,
        {
            "version": 1,
            "key_id": issued.key_id,
            "credential": issued.credential,
            "tenant_id": str(tenant_id),
            "store_id": str(store_id),
            "device_id": str(device_id),
            "expires_at": issued.expires_at.isoformat(),
        },
    )
    print(f"PASS: private device credential bundle created at {destination}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap single-store local pilot data")
    parser.add_argument("--tenant-name", default="Local Pilot Tenant")
    parser.add_argument("--store-name", default="Local Pilot Store")
    parser.add_argument("--admin-login", default=os.getenv("ADMIN_BOOTSTRAP_LOGIN", "admin"))
    parser.add_argument("--device-count", type=int, default=1)
    parser.add_argument(
        "--device-credential-output",
        default=os.getenv("KIOSK_PROVISIONING_BUNDLE_FILE", str(DEFAULT_DEVICE_BUNDLE)),
        help="Repository-external 0600 JSON file used once to provision Kiosk 1.",
    )
    parser.add_argument(
        "--skip-device-credential",
        action="store_true",
        help="Provision Admin RBAC without issuing a Kiosk device credential.",
    )
    parser.add_argument(
        "--generate-admin-password",
        action="store_true",
        help="Generate a strong password into a private repository-external bundle.",
    )
    parser.add_argument(
        "--admin-credential-output",
        default=os.getenv("ADMIN_PROVISIONING_BUNDLE_FILE", str(DEFAULT_ADMIN_BUNDLE)),
        help="Repository-external 0600 JSON file for a generated Admin login.",
    )
    parser.add_argument(
        "--write-pilot-env",
        action="store_true",
        help="Create a complete private local-pilot environment file outside the repository.",
    )
    parser.add_argument(
        "--pilot-env-output",
        default=os.getenv("LOCAL_PILOT_ENV_FILE", str(DEFAULT_PILOT_ENV)),
        help="Repository-external 0600 local-pilot environment file.",
    )
    parser.add_argument(
        "--scope-only",
        action="store_true",
        help="Provision tenant/store/device only; do not request or modify an Admin password.",
    )
    args = parser.parse_args(argv)

    from modules.runtime_persistence import load_environment_files

    load_environment_files(REPOSITORY_ROOT)
    os.environ.setdefault("DATABASE_BACKEND", "postgresql")
    os.environ.setdefault("DATABASE_TOPOLOGY", "single")
    from capabilities.identity_access import interface as admin_identity_service
    from modules.runtime_persistence.migrations import require_schema_head
    from repositories import postgres_utils

    if not postgres_utils.use_postgres():
        print("FAIL: DATABASE_BACKEND must be postgresql")
        return 1
    if not postgres_utils.database_url():
        print("FAIL: DATABASE_URL is required")
        return 1

    require_schema_head()
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

    if args.scope_only:
        print("PASS: tenant/store/device bootstrap complete; Admin identity unchanged")
        return 0

    login = admin_identity_service.normalize_admin_login(args.admin_login)
    from repositories import admin_identity_repository

    existing = admin_identity_repository.find_admin_user(tenant_id, login)
    permissions = admin_identity_service.sync_admin_permission_catalog()
    if existing is None:
        try:
            password = (
                _generated_admin_password(Path(args.admin_credential_output), login)
                if args.generate_admin_password
                else _password()
            )
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            print(f"FAIL: Admin credential provisioning failed: {exc}")
            return 1
        if len(password) < 12:
            print("FAIL: admin password must contain at least 12 characters")
            return 1
        user_id = uuid4()
        admin_identity_repository.create_admin_user(
            user_id=user_id,
            tenant_id=tenant_id,
            login_identity=login,
            display_name="Pilot Admin",
            password_hash=admin_identity_service.hash_admin_password(password),
        )
        print("PASS: created admin user (password not printed)")
    else:
        user_id = existing["id"]
        print("PASS: admin user already exists (not overwritten)")

    role_id = _ensure_admin_role(tenant_id, user_id, permissions)
    print(f"PASS: admin RBAC synchronized (role_id={role_id})")

    if not args.skip_device_credential:
        try:
            _issue_device_bundle(
                output_path=Path(args.device_credential_output),
                tenant_id=tenant_id,
                store_id=store_id,
                device_id=device_id,
                admin_user_id=user_id,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"FAIL: device credential provisioning failed: {exc}")
            return 1

    if args.write_pilot_env:
        try:
            _write_pilot_environment(
                output_path=Path(args.pilot_env_output),
                tenant_id=tenant_id,
                store_id=store_id,
                device_id=device_id,
                admin_login=login,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"FAIL: Pilot environment provisioning failed: {exc}")
            return 1

    print("PASS: tenant/store/device bootstrap complete")
    print(f"INFO: tenant_id={tenant_id}")
    print(f"INFO: store_id={store_id}")
    print(f"INFO: device_id={device_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
