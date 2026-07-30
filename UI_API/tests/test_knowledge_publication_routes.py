from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from models.commercial_scope import CommercialScope
from modules.knowledge_publication import KnowledgePublicationModule, SQLitePublicationStore


class RoutePublicationJobs:
    def enqueue(self, *, attempt_id, scope):
        return f"job-{attempt_id}"


def _attempt_id_for(publication, scope, item_id):
    """自動發布產生的 attempt_id 不再由呼叫端拿到，改從模組本身查。"""

    attempts = publication._store.list_attempts(scope=scope, limit=20)
    return next(row["attempt_id"] for row in attempts if row["item_id"] == item_id)


def test_knowledge_routes_use_publication_module_as_the_only_state_owner(
    tmp_path, monkeypatch
):
    from backend import app_factory
    from routes import v1_routes

    tenant_id = uuid4()
    store_id = uuid4()
    principal = SimpleNamespace(
        user_id=uuid4(),
        tenant_id=tenant_id,
        allowed_store_ids=(store_id,),
        roles=("admin",),
        permissions=("rag.read", "rag.write", "rag.publish"),
        session_id="test-session",
        auth_method="test",
    )
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(tmp_path / "publication.sqlite3"),
        jobs=RoutePublicationJobs(),
    )
    monkeypatch.setattr(app_factory.config, "validate_startup_config", lambda: None)
    monkeypatch.setattr(v1_routes, "authorize_admin_request", lambda *_args: principal)
    monkeypatch.setattr(
        v1_routes.knowledge_publication_runtime,
        "default_module",
        lambda: publication,
    )
    assert not hasattr(v1_routes.rag_knowledge_service, "create_knowledge")
    client = TestClient(app_factory.create_app())

    created_response = client.post(
        "/api/v1/rag/knowledge",
        json={
            "category": "store_and_hours",
            "content_type": "knowledge_article",
            "title": "Hours",
            "content": "Open until 21:00.",
            "override_near_duplicate": False,
        },
    )

    assert created_response.status_code == 200
    created = created_response.json()["data"]
    listed = client.get("/api/v1/rag/knowledge")
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["item_id"] == created["item_id"]

    # 儲存即發布（ADR-0017）：建立時就已排入索引，操作者不需要再按一次發布。
    assert created["autopublish"] == {"published": True, "reason": ""}
    assert listed.json()["data"]["items"][0]["status"] == "indexing"

    # 已在索引中的項目再次送出發布會被跳過，而不是重複排入。
    published = client.post(
        "/api/v1/rag/knowledge/publish",
        json={"item_ids": [created["item_id"]], "retry_failures_only": False},
    )
    assert published.status_code == 200
    assert published.json()["data"]["results"][0]["status"] == "skipped"
    attempt_id = _attempt_id_for(publication, CommercialScope(tenant_id, store_id), created["item_id"])

    resumed = client.post(
        f"/api/v1/rag/knowledge/publication-attempts/{attempt_id}/resume"
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"] == {
        "attempt_id": attempt_id,
        "status": "indexing",
        "phase": "build",
        "job_id": f"job-{attempt_id}",
    }
