"""Trusted provisioning commands for the Admin identity foundation."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from capabilities.identity_access import interface as admin_identity_service
from repositories import admin_audit_repository, admin_identity_repository
from utils.commercial_scope_config import resolve_commercial_scope


def _password_from_trusted_input() -> str:
    password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "")
    return password if password else getpass.getpass("Admin bootstrap password: ")


def sync_permissions() -> dict[str, object]:
    permissions = admin_identity_service.sync_admin_permission_catalog()
    return {"status": "ok", "permission_count": len(permissions)}


def bootstrap_admin(login_identity: str, display_name: str, role_code: str) -> dict[str, object]:
    scope = resolve_commercial_scope()
    normalized = admin_identity_service.normalize_admin_login(login_identity)
    if admin_identity_repository.find_admin_user(scope.tenant_id, normalized) is not None:
        raise RuntimeError("An Admin user with the configured identity already exists")
    user_id = uuid4()
    role_id = uuid4()
    admin_identity_repository.create_admin_user(
        user_id=user_id,
        tenant_id=scope.tenant_id,
        login_identity=normalized,
        display_name=display_name,
        password_hash=admin_identity_service.hash_admin_password(_password_from_trusted_input()),
    )
    permissions = admin_identity_service.sync_admin_permission_catalog()
    admin_identity_repository.create_admin_role(
        role_id=role_id,
        tenant_id=scope.tenant_id,
        code=role_code,
        name="Bootstrap Administrator",
    )
    for permission_id in permissions.values():
        admin_identity_repository.grant_permission_to_role(scope.tenant_id, role_id, permission_id)
    admin_identity_repository.assign_admin_role(
        assignment_id=uuid4(),
        tenant_id=scope.tenant_id,
        user_id=user_id,
        role_id=role_id,
        store_id=None,
    )
    admin_audit_repository.append_admin_audit_scoped(
        {
            "audit_id": f"aud_{uuid4().hex}",
            "actor": str(user_id),
            "action": "admin_bootstrap_created",
            "target_type": "admin_user",
            "target_id": str(user_id),
            "metadata": {"role_id": str(role_id), "permission_count": len(permissions)},
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        scope,
    )
    return {
        "status": "ok",
        "user_id": str(user_id),
        "tenant_id": str(scope.tenant_id),
        "role_id": str(role_id),
        "permission_count": len(permissions),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage trusted Admin identity provisioning")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("sync-permissions")
    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--login", required=True)
    bootstrap.add_argument("--display-name", default="")
    bootstrap.add_argument("--role-code", default="bootstrap-admin")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = (
        sync_permissions()
        if args.command == "sync-permissions"
        else bootstrap_admin(args.login, args.display_name, args.role_code)
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
