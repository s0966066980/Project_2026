"""Admin audit logging for high-risk admin actions."""

from datetime import datetime
from uuid import uuid4

from models.commercial_scope import CommercialScope
from modules.identity.application import scope_from_admin_principal
from repositories import admin_audit_repository


def _actor_from_request(request) -> str:
    if request is None:
        return "admin"
    principal = getattr(getattr(request, "state", None), "admin_principal", None)
    if principal is not None:
        return str(principal.user_id)
    device_principal = getattr(getattr(request, "state", None), "device_principal", None)
    if device_principal is not None:
        return str(device_principal.device_id)
    if request.headers.get("X-Kiosk-Token") or request.headers.get("X-Pos-Token"):
        return "kiosk"
    return "system"


def _request_metadata(request) -> dict:
    if request is None:
        return {}
    client = getattr(request, "client", None)
    return {
        "request_ip": getattr(client, "host", "") if client else "",
        "user_agent": request.headers.get("user-agent", ""),
    }


def record_admin_action(
    action: str,
    *,
    target_type: str,
    target_id: str,
    request=None,
    metadata: dict | None = None,
    scope: CommercialScope | None = None,
) -> dict:
    record = {
        "audit_id": f"aud_{uuid4().hex}",
        "actor": str(_actor_from_request(request) or "admin"),
        "action": str(action or ""),
        "target_type": str(target_type or ""),
        "target_id": str(target_id or ""),
        "metadata": {
            **_request_metadata(request),
            **(metadata or {}),
        },
        "created_at": datetime.now().isoformat(),
    }
    principal = getattr(getattr(request, "state", None), "admin_principal", None)
    resolved_scope = scope or (scope_from_admin_principal(principal) if principal is not None else None)
    if resolved_scope is not None:
        return admin_audit_repository.append_admin_audit_scoped(record, resolved_scope)
    return admin_audit_repository.append_admin_audit(record)


def list_admin_audits(limit: int = 200, scope: CommercialScope | None = None) -> list:
    if scope is not None:
        return admin_audit_repository.get_admin_audits_scoped(scope, limit=limit)
    return admin_audit_repository.get_admin_audits(limit=limit)
