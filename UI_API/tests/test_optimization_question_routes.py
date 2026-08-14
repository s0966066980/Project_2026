import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.optimization_lab.module import OptimizationLabModule
from modules.optimization_lab.sqlite_store import SQLiteOptimizationLabStore
from routes import optimization_lab_routes

pytestmark = [pytest.mark.contract]


def test_diagnostic_question_http_surface_enforces_separate_manage_permission(tmp_path, monkeypatch):
    module = OptimizationLabModule(store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"))
    allow_manage = [False]

    def fake_authorize(_request, permission):
        if permission == "optimization.manage" and not allow_manage[0]:
            raise HTTPException(status_code=403, detail={"code": "permission_denied"})
        return object()

    monkeypatch.setattr(optimization_lab_routes, "authorize_admin_request", fake_authorize)
    monkeypatch.setattr(optimization_lab_routes, "scope_from_admin_principal", lambda _principal: LEGACY_DEFAULT_SCOPE)
    monkeypatch.setattr(optimization_lab_routes.optimization_runtime, "default_module", lambda: module)

    with TestClient(app) as client:
        listed = client.get("/api/v1/optimization/questions")
        assert listed.status_code == 200
        assert listed.json()["questions"][0]["prompt"] == "診斷今日語音對話"

        denied = client.post(
            "/api/v1/optimization/questions",
            json={"display_name": "RAG 缺口", "prompt": "找出未命中的問題"},
        )
        assert denied.status_code == 403

        allow_manage[0] = True
        created = client.post(
            "/api/v1/optimization/questions",
            json={"display_name": "RAG 缺口", "prompt": "找出未命中的問題"},
        )
        assert created.status_code == 201
        question_id = created.json()["question"]["question_id"]

        updated = client.put(
            f"/api/v1/optimization/questions/{question_id}",
            json={"display_name": "RAG 缺口回顧", "prompt": "診斷未命中的常見問題"},
        )
        assert updated.status_code == 200
        assert updated.json()["question"]["display_name"] == "RAG 缺口回顧"

        deleted = client.delete(f"/api/v1/optimization/questions/{question_id}")
        assert deleted.status_code == 204


def test_diagnostic_question_routes_are_versioned_and_complete():
    paths = {route.path for route in optimization_lab_routes.create_router().routes}
    assert {
        "/api/v1/optimization/questions",
        "/api/v1/optimization/questions/{question_id}",
        "/api/v1/optimization/latest",
        "/api/v1/optimization/candidate",
        "/api/v1/optimization/candidate/{candidate_id}/abandon",
        "/api/v1/optimization/candidate/{candidate_id}",
        "/api/v1/optimization/candidate/{candidate_id}/confirm",
    } <= paths


def test_selected_question_runs_and_latest_result_is_readable(tmp_path, monkeypatch):
    module = OptimizationLabModule(store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"))
    question = module.create_diagnostic_question(
        scope=LEGACY_DEFAULT_SCOPE,
        display_name="語音診斷",
        prompt="診斷今日語音對話",
    )
    module.ingest_evidence(
        scope=LEGACY_DEFAULT_SCOPE,
        synthetic=True,
        payload={"observed_at": "2026-08-12T03:00:00+00:00", "voice_outcome": "success"},
    )
    monkeypatch.setattr(optimization_lab_routes, "authorize_admin_request", lambda _request, _permission: object())
    monkeypatch.setattr(optimization_lab_routes, "scope_from_admin_principal", lambda _principal: LEGACY_DEFAULT_SCOPE)
    monkeypatch.setattr(optimization_lab_routes.optimization_runtime, "default_module", lambda: module)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/optimization/simulations",
            json={
                "store_date": "2026-08-12",
                "timezone": "Asia/Taipei",
                "profile": "synthetic",
                "model": "synthetic-rule-v1",
                "effort": "standard",
                "data_scope": "synthetic_only",
                "question_id": question["question_id"],
            },
        )
        assert response.status_code == 200
        assert response.json()["diagnostic_question"]["prompt"] == "診斷今日語音對話"

        latest = client.get("/api/v1/optimization/latest")
        assert latest.status_code == 200
        assert latest.json()["report"]["report_id"] == response.json()["report_id"]


def test_pending_candidate_can_be_read_and_explicitly_abandoned(tmp_path, monkeypatch):
    module = OptimizationLabModule(store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"))
    module._store.create_candidate(
        scope=LEGACY_DEFAULT_SCOPE,
        record={
            "candidate_id": "candidate_route",
            "report_id": "report_route",
            "status": "pending",
            "action": "create",
            "proposed": {"title": "測試", "content": "內容"},
            "created_at": "2026-08-12T04:00:00+00:00",
            "expires_at": "2026-09-11T04:00:00+00:00",
        },
    )
    monkeypatch.setattr(optimization_lab_routes, "authorize_admin_request", lambda _request, _permission: object())
    monkeypatch.setattr(optimization_lab_routes, "scope_from_admin_principal", lambda _principal: LEGACY_DEFAULT_SCOPE)
    monkeypatch.setattr(optimization_lab_routes.optimization_runtime, "default_module", lambda: module)

    with TestClient(app) as client:
        candidate = client.get("/api/v1/optimization/candidate").json()["candidate"]
        assert candidate["candidate_id"] == "candidate_route"
        abandoned = client.post("/api/v1/optimization/candidate/candidate_route/abandon")
        assert abandoned.status_code == 200
        assert abandoned.json()["candidate"]["status"] == "abandoned"


def test_candidate_edit_and_confirm_require_rag_permissions(tmp_path, monkeypatch):
    class AcceptingOfflineEvaluator:
        def evaluate(self, *, snapshot):
            return True

    class KnowledgePort:
        def create_draft(self, **kwargs):
            return {"item_id": "knowledge-route", "row_revision": 1}

        def request_publication(self, **kwargs):
            return {"status": "indexing"}

    knowledge = KnowledgePort()
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        offline_evaluator=AcceptingOfflineEvaluator(),
        knowledge=knowledge,
    )
    module._store.create_candidate(
        scope=LEGACY_DEFAULT_SCOPE,
        record={
            "candidate_id": "candidate_confirm",
            "report_id": "report_confirm",
            "status": "pending",
            "action": "create",
            "proposed": {
                "title": "舊標題",
                "category": "other",
                "content_type": "question_answer",
                "content": "舊內容",
            },
            "evidence_ids": [],
            "offline_acceptance": "passed",
            "created_at": "2026-08-12T04:00:00+00:00",
            "expires_at": "2026-09-11T04:00:00+00:00",
        },
    )
    calls = []

    def fake_authorize(_request, permission):
        calls.append(permission)
        return object()

    monkeypatch.setattr(optimization_lab_routes, "authorize_admin_request", fake_authorize)
    monkeypatch.setattr(optimization_lab_routes, "scope_from_admin_principal", lambda _principal: LEGACY_DEFAULT_SCOPE)
    monkeypatch.setattr(optimization_lab_routes.optimization_runtime, "default_module", lambda: module)

    with TestClient(app) as client:
        edited = client.put(
            "/api/v1/optimization/candidate/candidate_confirm",
            json={
                "title": "新標題",
                "category": "other",
                "content_type": "question_answer",
                "content": "新內容",
            },
        )
        assert edited.status_code == 200
        confirmed = client.post("/api/v1/optimization/candidate/candidate_confirm/confirm")
        assert confirmed.status_code == 200
        assert confirmed.json()["candidate"]["status"] == "confirmed"

    assert "rag.write" in calls
    assert "rag.publish" in calls
