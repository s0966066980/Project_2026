from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.commercial_scope import LEGACY_DEFAULT_SCOPE


def test_admin_can_preview_formal_store_scoped_index(monkeypatch):
    from routes import v1_routes

    calls = []

    class FakeChecks:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return {
                "check_id": "arc_test",
                "method": kwargs["method"],
                "top_k": kwargs["top_k"],
                "relevance_policy": kwargs["relevance_policy"],
                "fallback_used": "",
                "latency_ms": 4.2,
                "total": 1,
                "results": [
                    {
                        "rank": 1,
                        "id": "breakfast_policy",
                        "content": "早餐供應到 10:30",
                        "source_type": "question_answer",
                        "metadata": {},
                        "match_types": [kwargs["method"]],
                        "score": 0.9,
                    }
                ],
            }

    monkeypatch.setattr(v1_routes, "_scope", lambda request, permission: LEGACY_DEFAULT_SCOPE)
    monkeypatch.setattr(
        v1_routes,
        "_meta",
        lambda request: v1_routes.ApiMeta(request_id="req_test", timestamp=v1_routes.datetime.now(v1_routes.timezone.utc)),
    )
    monkeypatch.setattr(
        v1_routes.retrieval_check_runtime,
        "default_module",
        lambda: FakeChecks(),
    )
    app = FastAPI()
    app.include_router(v1_routes.create_router())
    client = TestClient(app)

    response = client.post(
        "/api/v1/rag/retrieval/test",
        json={"query": "早餐供應到幾點？", "method": "bm25", "top_k": 5, "relevance_policy": "balanced"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["method"] == "bm25"
    assert calls[0]["scope"] == LEGACY_DEFAULT_SCOPE
    assert calls[0]["top_k"] == 5


def test_confirming_retrieval_result_requires_publish_permission(monkeypatch):
    from routes import v1_routes

    permissions = []

    class FakeChecks:
        def confirm(self, **kwargs):
            return {"check_id": kwargs["check_id"], "confirmed_by": kwargs["actor"]}

    def fake_scope(request, permission):
        permissions.append(permission)
        return LEGACY_DEFAULT_SCOPE

    monkeypatch.setattr(v1_routes, "_scope", fake_scope)
    monkeypatch.setattr(
        v1_routes,
        "_meta",
        lambda request: v1_routes.ApiMeta(request_id="req_test", timestamp=v1_routes.datetime.now(v1_routes.timezone.utc)),
    )
    monkeypatch.setattr(
        v1_routes.retrieval_check_runtime,
        "default_module",
        lambda: FakeChecks(),
    )
    app = FastAPI()
    app.include_router(v1_routes.create_router())
    client = TestClient(app)

    response = client.post("/api/v1/rag/retrieval/checks/arc_test/confirm")

    assert response.status_code == 200
    assert response.json()["data"]["check_id"] == "arc_test"
    assert permissions == ["rag.publish"]


def test_rag_test_rejects_invalid_method_and_oversized_query(monkeypatch):
    from routes import v1_routes

    monkeypatch.setattr(v1_routes, "_scope", lambda request, permission: LEGACY_DEFAULT_SCOPE)
    app = FastAPI()
    app.include_router(v1_routes.create_router())
    client = TestClient(app)

    assert client.post("/api/v1/rag/retrieval/test", json={"query": "test", "method": "unknown"}).status_code == 422
    assert client.post("/api/v1/rag/retrieval/test", json={"query": "x" * 2001, "method": "dense"}).status_code == 422
