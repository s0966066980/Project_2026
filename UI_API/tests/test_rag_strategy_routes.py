from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeRag:
    def __init__(self):
        self.calls = []

    async def search(self, query, *, strategy, top_k):
        self.calls.append((query, strategy, top_k))
        return {
            "strategy": strategy,
            "total": 1,
            "results": [{
                "rank": 1,
                "id": "breakfast_policy",
                "content": "早餐供應到 10:30",
                "source_type": "policy",
                "metadata": {},
                "match_types": [strategy],
                "score": 0.9,
            }],
        }


def test_admin_can_preview_a_selected_rag_strategy(monkeypatch):
    from routes import rag_routes

    fake = FakeRag()
    monkeypatch.setattr(rag_routes, "get_rag", lambda: fake)
    monkeypatch.setattr(rag_routes, "authorize_admin_request", lambda request, permission: object())
    monkeypatch.setattr(rag_routes, "check_rate_limit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(rag_routes.create_router({}))
    client = TestClient(app)

    response = client.post("/api/rag/test", json={
        "query": "  早餐供應到幾點？  ",
        "strategy": "bm25",
        "top_k": 5,
    })

    assert response.status_code == 200
    assert response.json()["strategy"] == "bm25"
    assert response.json()["results"][0]["id"] == "breakfast_policy"
    assert fake.calls == [("早餐供應到幾點？", "bm25", 5)]


def test_rag_strategy_preview_rejects_invalid_strategy_and_oversized_query(monkeypatch):
    from routes import rag_routes

    monkeypatch.setattr(rag_routes, "authorize_admin_request", lambda request, permission: object())
    app = FastAPI()
    app.include_router(rag_routes.create_router({}))
    client = TestClient(app)

    assert client.post("/api/rag/test", json={"query": "test", "strategy": "unknown"}).status_code == 422
    assert client.post("/api/rag/test", json={"query": "x" * 501, "strategy": "dense"}).status_code == 422
