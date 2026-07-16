"""RAG 知識庫管理路由。"""

from fastapi import APIRouter, Body, Request
from realtime import event_bus

from services import admin_audit_service, promotion_service, rag_alert_service, rag_document_service, rag_review_service
from services.commercial_context_service import scope_from_admin_principal
from services.rag_provider import get_rag
from utils.auth_utils import authorize_admin_request, check_rate_limit


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/rag", tags=["rag"])

    def _admin_actor(request: Request) -> str:
        return (request.headers.get("X-Admin-User") or request.headers.get("X-Admin-Token") or "admin")[:80]

    async def _publish_alert_if_new(result: dict):
        alert_info = result.get("alert") if isinstance(result, dict) else {}
        if not isinstance(alert_info, dict) or not alert_info.get("created"):
            return
        alert = alert_info.get("alert") if isinstance(alert_info.get("alert"), dict) else {}
        if alert:
            await event_bus.publish_to_admin("rag_alert", {"alert": alert})

    @router.get("/status")
    async def rag_status():
        result = await rag_document_service.health_status()
        await _publish_alert_if_new(result)
        return result

    @router.get("/docs")
    async def list_docs(request: Request):
        authorize_admin_request(request, "rag.read")
        docs = await get_rag().list_documents()
        return {"status": "ok", "docs": docs, "total": len(docs)}

    @router.post("/docs")
    async def add_doc(request: Request, payload: dict = Body(...)):
        authorize_admin_request(request, "rag.write")
        if not payload.get("direct_write"):
            review, errors = rag_review_service.create_review(payload, actor=_admin_actor(request))
            if errors:
                return {"status": "error", "errors": errors}
            return {
                "status": "pending_review",
                "message": "文件已建立為草稿，發布後才會進入 rag_documents 並可重建到 Chroma。",
                "review": review,
            }
        content = str(payload.get("content") or "").strip()
        if not content:
            return {"status": "error", "message": "content 不可為空"}
        source_id = payload.get("source_id") or None
        source_type = str(payload.get("source_type") or "manual")
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
        doc_id = await get_rag().add_document(content, source_id, source_type, metadata)
        return {"status": "ok", "id": doc_id}

    @router.get("/reviews")
    async def list_reviews(request: Request, status: str = ""):
        authorize_admin_request(request, "rag.read")
        reviews = rag_review_service.list_reviews(status=status)
        return {"status": "ok", "reviews": reviews, "total": len(reviews)}

    @router.get("/alerts")
    async def list_alerts(request: Request, status: str = "", limit: int = 100):
        authorize_admin_request(request, "rag.read")
        alerts = rag_alert_service.list_alerts(status=status, limit=limit)
        return {"status": "ok", "alerts": alerts, "total": len(alerts)}

    @router.post("/alerts/{alert_id}/ack")
    async def acknowledge_alert(request: Request, alert_id: str):
        authorize_admin_request(request, "rag.review")
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
        authorize_admin_request(request, "rag.review")
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

    @router.post("/reviews")
    async def create_review(request: Request, payload: dict = Body(...)):
        authorize_admin_request(request, "rag.write")
        review, errors = rag_review_service.create_review(payload, actor=_admin_actor(request))
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "review": review}

    @router.put("/reviews/{review_id}")
    async def update_review(request: Request, review_id: str, payload: dict = Body(...)):
        authorize_admin_request(request, "rag.write")
        review, errors = rag_review_service.update_review(review_id, payload, actor=_admin_actor(request))
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "review": review}

    @router.post("/reviews/{review_id}/approve")
    async def approve_review(request: Request, review_id: str):
        authorize_admin_request(request, "rag.review")
        review, errors = rag_review_service.approve_review(review_id, actor=_admin_actor(request))
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "review": review}

    @router.post("/reviews/{review_id}/publish")
    async def publish_review(request: Request, review_id: str):
        authorize_admin_request(request, "rag.review")
        review, errors = rag_review_service.publish_review(review_id, actor=_admin_actor(request))
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "review": review}

    @router.post("/reviews/{review_id}/reject")
    async def reject_review(request: Request, review_id: str, payload: dict = Body(default={})):
        authorize_admin_request(request, "rag.review")
        review, errors = rag_review_service.reject_review(
            review_id,
            str(payload.get("reason") or ""),
            actor=_admin_actor(request),
        )
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "review": review}

    @router.post("/reviews/{review_id}/archive")
    async def archive_review(request: Request, review_id: str):
        authorize_admin_request(request, "rag.review")
        review, errors = rag_review_service.archive_review(review_id, actor=_admin_actor(request))
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "review": review}

    @router.post("/rebuild")
    async def rebuild_docs(request: Request, payload: dict = Body(default={})):
        authorize_admin_request(request, "rag.write")
        check_rate_limit(request, "rag_rebuild", limit=3, window_seconds=600)
        selected_source_ids = payload.get("selected_source_ids") if "selected_source_ids" in payload else None
        if selected_source_ids is not None and not isinstance(selected_source_ids, list):
            return {"status": "error", "errors": ["selected_source_ids 必須是陣列"]}
        result = await rag_document_service.rebuild_from_source_documents(selected_source_ids=selected_source_ids)
        await _publish_alert_if_new(result)
        return result

    @router.get("/validate")
    async def validate_docs(request: Request):
        authorize_admin_request(request, "rag.read")
        return rag_document_service.validate_source_documents(include_documents=True)

    @router.get("/rebuild/preview")
    async def preview_rebuild(request: Request):
        authorize_admin_request(request, "rag.read")
        return rag_document_service.validate_source_documents(include_documents=True)

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
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "promotion": record}

    @router.put("/promotions/{offer_id}")
    async def update_promotion(request: Request, offer_id: str, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "rag.write")
        scope = scope_from_admin_principal(principal)
        record, errors = promotion_service.save_promotion(payload, existing_offer_id=offer_id, scope=scope)
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "promotion": record}

    @router.patch("/promotions/{offer_id}/status")
    async def patch_promotion_status(request: Request, offer_id: str, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "rag.write")
        scope = scope_from_admin_principal(principal)
        record, errors = promotion_service.update_promotion_status(offer_id, str(payload.get("status") or ""), scope)
        if errors:
            return {"status": "error", "errors": errors}
        return {"status": "ok", "promotion": record}

    @router.delete("/promotions/{offer_id}")
    async def delete_promotion(request: Request, offer_id: str):
        principal = authorize_admin_request(request, "rag.write")
        scope = scope_from_admin_principal(principal)
        deleted = promotion_service.delete_promotion(offer_id, scope)
        return {"status": "ok" if deleted else "not_found", "deleted": deleted}

    @router.delete("/docs/{doc_id}")
    async def delete_doc(request: Request, doc_id: str):
        authorize_admin_request(request, "rag.write")
        ok = await get_rag().delete_document(doc_id)
        if ok:
            rag_document_service.exclude_source_from_index(doc_id)
        return {"status": "ok" if ok else "not_found"}

    @router.delete("/docs")
    async def clear_docs(request: Request):
        authorize_admin_request(request, "rag.write")
        return await rag_document_service.clear_index()

    return router
