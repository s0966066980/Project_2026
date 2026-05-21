import asyncio
import os
import tempfile
import time

from fastapi import APIRouter, Body, File, Form, Request, UploadFile

import config
import database
from repositories import log_repository
from services import rag_review_service
from utils.auth_utils import require_admin_token
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["rag"])

    @router.get("/rag_docs")
    async def get_rag_docs():
        review_logs = await asyncio.to_thread(log_repository.get_rag_review_logs)
        indexed_review_logs = []
        for idx, log in enumerate(review_logs):
            row = dict(log)
            row["_index"] = idx
            indexed_review_logs.append(row)
        return {
            "docs": await asyncio.to_thread(database.get_rag_docs),
            "review_logs": indexed_review_logs[-300:]
        }

    @router.post("/rag_docs")
    async def create_rag_doc(request: Request, payload: dict = Body(...)):
        require_admin_token(request)
        source_text = (payload.get("source_text") or "").strip()
        source_id = (payload.get("source_id") or f"manual_{int(time.time())}").strip()
        if not source_text:
            return {"status": "error", "message": "source_text is required"}
        review_result = await rag_review_service.review_rag_text(
            source_text, "manual", source_id, deps["ollama_semaphore"]
        )
        doc = await asyncio.to_thread(
            database.upsert_reviewed_rag_doc, "manual", source_id, source_text, review_result
        )
        await deps["safe_rebuild_rag"]("manual RAG doc")
        deps["recommend_cache"].clear()
        return {"status": "success", "doc": doc}

    @router.post("/rag_pdf")
    async def upload_rag_pdf(
        request: Request,
        pdf: UploadFile = File(...),
        review: str = Form(default="false")
    ):
        require_admin_token(request)
        if not (pdf.filename or "").lower().endswith(".pdf"):
            return {"status": "error", "message": "只支援 PDF 檔案。"}
        temp_pdf_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                temp_pdf_path = tmp.name
            pdf_bytes = await pdf.read()
            await asyncio.to_thread(write_binary_file, temp_pdf_path, pdf_bytes)
            chunks = await asyncio.to_thread(database.load_pdf_chunks, temp_pdf_path, pdf.filename or "uploaded.pdf")
            saved = []
            should_review = review.lower() == "true" and config.get("RAG_REVIEW_ENABLED", True)
            for idx, chunk in enumerate(chunks):
                metadata = chunk.get("metadata", {})
                source_id = f"{pdf.filename or 'uploaded.pdf'}:{metadata.get('page', '-')}:chunk_{idx + 1}"
                source_text = chunk.get("text", "")
                if should_review:
                    review_result = await rag_review_service.review_rag_text(
                        source_text, "pdf", source_id, deps["ollama_semaphore"]
                    )
                else:
                    review_result = {
                        "status": "approved",
                        "reviewed_text": source_text,
                        "notes": "PDF loader chunk imported without Ollama rewrite.",
                    }
                saved.append(await asyncio.to_thread(
                    database.upsert_reviewed_rag_doc,
                    "pdf",
                    source_id,
                    source_text,
                    review_result,
                    metadata
                ))
            await deps["safe_rebuild_rag"]("PDF RAG upload")
            deps["recommend_cache"].clear()
            return {"status": "success", "chunks": len(saved), "docs": saved[:20]}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)

    @router.delete("/rag_docs/{doc_id}")
    async def delete_rag_doc(request: Request, doc_id: str):
        require_admin_token(request)
        deleted = await asyncio.to_thread(database.delete_rag_doc, doc_id)
        if deleted:
            deps["recommend_cache"].clear()
        return {"status": "success" if deleted else "not_found"}

    @router.delete("/rag_docs")
    async def clear_rag_docs(request: Request):
        require_admin_token(request)
        await asyncio.to_thread(database.clear_rag_storage)
        deps["recommend_cache"].clear()
        return {"status": "success"}

    @router.delete("/rag_review_logs/{log_index}")
    async def delete_rag_review_log(request: Request, log_index: int):
        require_admin_token(request)
        deleted = await asyncio.to_thread(log_repository.delete_rag_review_log, log_index)
        return {"status": "success" if deleted else "not_found"}

    return router
