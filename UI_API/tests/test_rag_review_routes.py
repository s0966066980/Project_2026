"""Legacy RAG management routes stay removed after the v1 consolidation."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import rag_routes


def test_legacy_rag_management_routes_are_not_registered() -> None:
    app = FastAPI()
    app.include_router(rag_routes.create_router({}))
    client = TestClient(app)

    for method, path in (
        ("get", "/api/rag/docs"),
        ("post", "/api/rag/test"),
        ("get", "/api/rag/faqs"),
        ("get", "/api/rag/knowledge-gaps"),
        ("get", "/api/rag/reviews"),
        ("post", "/api/rag/rebuild"),
        ("get", "/api/rag/validate"),
    ):
        assert getattr(client, method)(path).status_code == 404
