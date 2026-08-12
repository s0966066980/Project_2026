"""Versioned Admin health report and incident actions.

`/api/v1/operations/service-health` answers "can a customer order right now",
one row per service. This is the other health view: the operational report
built from the Admin audit trail, including the incidents an operator can
acknowledge or escalate. The two are not interchangeable, which is why the
report needed its own versioned surface when the unversioned `/api/admin/*`
compatibility routes were withdrawn.
"""

import asyncio

from fastapi import APIRouter, Body, HTTPException, Request

from capabilities.identity_access import scope_from_admin_principal
from capabilities.operations_configuration import interface as operations
from utils.auth_utils import authorize_admin_request, check_rate_limit


def create_router(_deps: dict | None = None, *, prefix: str = "/api/v1/admin/health") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["v1-admin-health"])

    @router.get("")
    async def get_admin_health(request: Request):
        principal = authorize_admin_request(request, "operations.read")
        scope = scope_from_admin_principal(principal)
        actions = await asyncio.to_thread(operations.list_admin_audits, 500, scope)
        return await operations.build_admin_health(actions)

    async def record_health_incident_action(request: Request, incident_id: str, action: str, body: dict) -> dict:
        principal = authorize_admin_request(request, "operations.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_health_incident_action", limit=30)
        actions = await asyncio.to_thread(operations.list_admin_audits, 500, scope)
        current = await operations.build_admin_health(actions)
        incidents = current.get("operational", {}).get("incidents", [])
        incident = next((row for row in incidents if row.get("incident_id") == incident_id), None)
        if incident is None:
            raise HTTPException(status_code=404, detail="health incident is no longer active")
        reason = str((body or {}).get("reason") or "").strip()[:500]
        await asyncio.to_thread(
            operations.record_admin_action,
            action,
            target_type="health_incident",
            target_id=incident_id,
            request=request,
            metadata={"reason": reason, "check_key": incident.get("check_key", "")},
            scope=scope,
        )
        updated_actions = await asyncio.to_thread(operations.list_admin_audits, 500, scope)
        return await operations.build_admin_health(updated_actions)

    @router.post("/incidents/{incident_id}/acknowledge")
    async def acknowledge_health_incident(request: Request, incident_id: str, body: dict = Body(default={})):
        return await record_health_incident_action(request, incident_id, "health.incident.acknowledge", body)

    @router.post("/incidents/{incident_id}/escalate")
    async def escalate_health_incident(request: Request, incident_id: str, body: dict = Body(default={})):
        return await record_health_incident_action(request, incident_id, "health.incident.escalate", body)

    return router
