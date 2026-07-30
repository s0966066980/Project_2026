"""Compatibility RAG routes.

Knowledge management and retrieval testing live exclusively under /api/v1/rag.
This router retains only operational alerts and the separate promotion surface.
"""

from fastapi import APIRouter, Body, Request
from realtime import event_bus

from services import admin_audit_service, promotion_service, rag_alert_service, rag_document_service
from services.commercial_context_service import scope_from_admin_principal
from utils.auth_utils import authorize_admin_request


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/rag", tags=["rag-compatibility"])

    def _admin_actor(request: Request) -> str:
        principal = getattr(request.state, "admin_principal", None)
        return str(getattr(principal, "user_id", None) or "admin")[:80]

    async def _publish_alert_if_new(result: dict):
        alert_info = result.get("alert") if isinstance(result, dict) else {}
        if not isinstance(alert_info, dict) or not alert_info.get("created"):
            return
        alert = alert_info.get("alert") if isinstance(alert_info.get("alert"), dict) else {}
        if alert:
            await event_bus.publish_to_admin("rag_alert", {"alert": alert})

    @router.get("/status")
    async def rag_status(request: Request):
        authorize_admin_request(request, "rag.read")
        result = await rag_document_service.health_status()
        await _publish_alert_if_new(result)
        return result

    @router.get("/alerts")
    async def list_alerts(request: Request, status: str = "", limit: int = 100):
        authorize_admin_request(request, "rag.read")
        alerts = rag_alert_service.list_alerts(status=status, limit=limit)
        return {"status": "ok", "alerts": alerts, "total": len(alerts)}

    @router.post("/alerts/{alert_id}/ack")
    async def acknowledge_alert(request: Request, alert_id: str):
        authorize_admin_request(request, "rag.write")
        alert, errors = rag_alert_service.acknowledge_alert(alert_id, actor=_admin_actor(request))
        if errors:
            return {"status": "error", "errors": errors}
        admin_audit_service.record_admin_action(
            "rag_alert_acknowledged",
            target_type="rag_alert",
            target_id=alert_id,
            request=request,
            metadata={"alert_type": alert.get("alert_type", "") if alert else ""},
        )
        return {"status": "ok", "alert": alert}

    @router.post("/alerts/{alert_id}/resolve")
    async def resolve_alert(request: Request, alert_id: str):
        authorize_admin_request(request, "rag.write")
        alert, errors = rag_alert_service.resolve_alert(alert_id, actor=_admin_actor(request))
        if errors:
            return {"status": "error", "errors": errors}
        admin_audit_service.record_admin_action(
            "rag_alert_resolved",
            target_type="rag_alert",
            target_id=alert_id,
            request=request,
            metadata={"alert_type": alert.get("alert_type", "") if alert else ""},
        )
        return {"status": "ok", "alert": alert}

    @router.get("/promotions")
    async def list_promotions(request: Request):
        principal = authorize_admin_request(request, "rag.read")
        scope = scope_from_admin_principal(principal)
        promotions = promotion_service.list_promotions(scope)
        return {"status": "ok", "promotions": promotions, "total": len(promotions)}

    @router.post("/promotions")
    async def create_promotion(request: Request, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "rag.write")
        scope = scope_from_admin_principal(principal)
        record, errors = promotion_service.save_promotion(payload, scope=scope)
        return {"status": "error", "errors": errors} if errors else {"status": "ok", "promotion": record}

    @router.put("/promotions/{offer_id}")
    async def update_promotion(request: Request, offer_id: str, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "rag.write")
        scope = scope_from_admin_principal(principal)
        record, errors = promotion_service.save_promotion(payload, existing_offer_id=offer_id, scope=scope)
        return {"status": "error", "errors": errors} if errors else {"status": "ok", "promotion": record}

    @router.patch("/promotions/{offer_id}/status")
    async def patch_promotion_status(request: Request, offer_id: str, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "rag.write")
        scope = scope_from_admin_principal(principal)
        record, errors = promotion_service.update_promotion_status(offer_id, str(payload.get("status") or ""), scope)
        return {"status": "error", "errors": errors} if errors else {"status": "ok", "promotion": record}

    @router.delete("/promotions/{offer_id}")
    async def delete_promotion(request: Request, offer_id: str):
        principal = authorize_admin_request(request, "rag.write")
        scope = scope_from_admin_principal(principal)
        deleted = promotion_service.delete_promotion(offer_id, scope)
        return {"status": "ok" if deleted else "not_found", "deleted": deleted}

    return router
