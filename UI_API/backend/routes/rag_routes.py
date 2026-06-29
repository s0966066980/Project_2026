"""RAG 知識庫管理路由。"""

from fastapi import APIRouter, Body, Request

from services.rag_provider import get_rag
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/rag", tags=["rag"])

    @router.get("/status")
    async def rag_status():
        rag = get_rag()
        count = await rag.count()
        return {
            "status": "ok",
            "enabled": True,
            "doc_count": count,
        }

    @router.get("/docs")
    async def list_docs(request: Request):
        require_admin_token(request)
        docs = await get_rag().list_documents()
        return {"status": "ok", "docs": docs, "total": len(docs)}

    @router.post("/docs")
    async def add_doc(request: Request, payload: dict = Body(...)):
        require_admin_token(request)
        content = str(payload.get("content") or "").strip()
        if not content:
            return {"status": "error", "message": "content 不可為空"}
        source_id = payload.get("source_id") or None
        source_type = str(payload.get("source_type") or "manual")
        doc_id = await get_rag().add_document(content, source_id, source_type)
        return {"status": "ok", "id": doc_id}

    @router.delete("/docs/{doc_id}")
    async def delete_doc(request: Request, doc_id: str):
        require_admin_token(request)
        ok = await get_rag().delete_document(doc_id)
        return {"status": "ok" if ok else "not_found"}

    @router.delete("/docs")
    async def clear_docs(request: Request):
        require_admin_token(request)
        deleted = await get_rag().clear_all()
        return {"status": "ok", "deleted": deleted}

    return router
