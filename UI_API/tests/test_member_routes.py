import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from repositories import admin_audit_repository, member_repository
    importlib.reload(admin_audit_repository)
    importlib.reload(member_repository)
    monkeypatch.setattr(admin_audit_repository, "ADMIN_AUDIT_PATH", str(tmp_path / "admin_audit_logs.json"))
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    from services import member_service
    importlib.reload(member_service)
    member_service._session_member.clear()
    from routes import member_routes
    importlib.reload(member_routes)
    app = FastAPI()
    app.include_router(member_routes.create_router({}))
    return TestClient(app)


def test_register_then_login(client):
    r = client.post("/api/member/register", data={"session_id": "s1", "phone": "0912345678", "nickname": "小明"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["member"]["nickname"] == "小明"
    assert r.json()["member"]["order_history_consent"] is True

    r2 = client.post("/api/member/login", data={"session_id": "s2", "phone": "0912345678"})
    assert r2.json()["found"] is True


def test_login_not_found(client):
    r = client.post("/api/member/login", data={"session_id": "s1", "phone": "0900000000"})
    assert r.json() == {"found": False}


def test_register_rejects_missing_consent(client):
    r = client.post("/api/member/register", data={
        "session_id": "s1",
        "phone": "0912345678",
        "nickname": "小明",
        "order_history_consent": "false",
        "personalization_consent": "true",
    })
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": "consent_required"}


def test_abandoned_order_route(client):
    client.post("/api/member/register", data={"session_id": "s1", "phone": "0912345678", "nickname": "小明"})
    r = client.post("/api/member/abandoned_order", data={
        "session_id": "s1",
        "cart_ids": '["MCD001"]',
        "cart_total": "155",
        "reason": "cancel_order",
    })
    body = r.json()
    assert r.status_code == 200
    assert body["ok"] is True
    assert body["member"]["history"][0]["is_completed"] is False
    assert body["member"]["history"][0]["order_status"] == "cancelled"


def test_admin_list_and_detail(client):
    client.post("/api/member/register", data={"session_id": "s1", "phone": "0912345678", "nickname": "小明"})
    rows = client.get("/api/members").json()
    assert isinstance(rows, list) and rows[0]["phone_masked"] == "0912-***-678"
    assert "phone" not in rows[0]
    member_ref = rows[0]["member_ref"]
    detail = client.get(f"/api/members/{member_ref}").json()
    assert detail["nickname"] == "小明"
    assert "phone" not in detail
    assert client.get("/api/members/0900000000").status_code == 404


def test_admin_export_and_audit(client):
    client.post("/api/member/register", data={"session_id": "s1", "phone": "0912345678", "nickname": "小明"})
    response = client.get("/api/members/export")
    assert response.status_code == 200
    assert "0912-***-678" in response.text
    assert "0912345678" not in response.text
    assert response.headers.get("X-Admin-Audit-Id", "").startswith("aud_")

    audits = client.get("/api/admin/audit_logs").json()
    assert audits[-1]["action"] == "member_export"


def test_admin_delete_records_writes_audit(client):
    client.post("/api/member/register", data={"session_id": "s1", "phone": "0912345678", "nickname": "小明"})
    member_ref = client.get("/api/members").json()[0]["member_ref"]
    response = client.delete(f"/api/members/{member_ref}/records")
    assert response.status_code == 200
    assert response.json()["audit_id"].startswith("aud_")

    audits = client.get("/api/admin/audit_logs").json()
    assert audits[-1]["action"] == "member_clear_records"
