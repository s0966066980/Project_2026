import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from repositories import member_repository
    importlib.reload(member_repository)
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

    r2 = client.post("/api/member/login", data={"session_id": "s2", "phone": "0912345678"})
    assert r2.json()["found"] is True


def test_login_not_found(client):
    r = client.post("/api/member/login", data={"session_id": "s1", "phone": "0900000000"})
    assert r.json() == {"found": False}


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
    detail = client.get("/api/members/0912345678").json()
    assert detail["nickname"] == "小明"
    assert client.get("/api/members/0900000000").status_code == 404
