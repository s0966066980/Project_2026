import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeRag:
    def __init__(self):
        self.added = []

    async def add_document(self, content, source_id=None, source_type="manual", metadata=None):
        self.added.append({
            "content": content,
            "source_id": source_id,
            "source_type": source_type,
            "metadata": metadata or {},
        })
        return source_id or "doc_id"


def _client(tmp_path, monkeypatch):
    from routes import rag_routes
    from services import rag_review_service
    importlib.reload(rag_review_service)
    importlib.reload(rag_routes)

    monkeypatch.setattr(rag_review_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    monkeypatch.setattr(rag_review_service.config, "LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    fake_rag = FakeRag()
    monkeypatch.setattr(rag_routes, "get_rag", lambda: fake_rag)

    app = FastAPI()
    app.include_router(rag_routes.create_router({}))
    return TestClient(app), fake_rag


def test_post_rag_docs_creates_review_by_default(tmp_path, monkeypatch):
    client, fake_rag = _client(tmp_path, monkeypatch)

    response = client.post("/api/rag/docs", json={
        "source_id": "faq_refund_policy",
        "source_type": "faq",
        "content": "退款請依現場公告辦理。",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending_review"
    assert data["review"]["status"] == "draft"
    assert fake_rag.added == []


def test_post_rag_docs_direct_write_is_explicit(tmp_path, monkeypatch):
    client, fake_rag = _client(tmp_path, monkeypatch)

    response = client.post("/api/rag/docs", json={
        "source_id": "manual_direct_debug",
        "source_type": "manual",
        "content": "除錯用直接寫入。",
        "direct_write": True,
    })

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fake_rag.added[0]["source_id"] == "manual_direct_debug"
