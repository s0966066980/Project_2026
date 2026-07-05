import importlib

import pytest


@pytest.fixture
def svc(tmp_path, monkeypatch):
    from repositories import member_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    from services import member_service
    importlib.reload(member_service)
    member_service._session_member.clear()
    return member_service


def test_normalize_phone(svc):
    assert svc.normalize_phone("0912-345-678") == "0912345678"
    assert svc.normalize_phone(" 0912345678 ") == "0912345678"
    assert svc.normalize_phone("12345") == ""
    assert svc.normalize_phone(None) == ""


def test_mask_phone(svc):
    assert svc.mask_phone("0912345678") == "0912-***-678"
    assert svc.mask_phone("xyz") == "xyz"


def test_login_not_found(svc):
    assert svc.login("s1", "0912345678") == {"found": False}


def test_login_invalid_phone(svc):
    assert svc.login("s1", "999")["found"] is False
    assert svc.login("s1", "999")["error"] == "invalid_phone"


def test_register_then_login_binds_session(svc):
    reg = svc.register("s1", "0912-345-678", "小明")
    assert reg["ok"] is True
    assert reg["member"]["nickname"] == "小明"
    assert reg["member"]["order_history_consent"] is True
    assert reg["member"]["personalization_consent"] is True
    assert svc.get_session_member("s1")["phone"] == "0912345678"
    out = svc.login("s2", "0912345678")
    assert out["found"] is True
    assert svc.get_session_member("s2")["phone"] == "0912345678"
    stored = svc.member_repository.get_member("0912345678")
    assert stored["login_count"] == 2
    assert stored["last_login_at"]
    assert stored["data_retention_until"]


def test_register_default_nickname(svc):
    reg = svc.register("s1", "0955000321", "")
    assert reg["member"]["nickname"] == "會員0321"


def test_register_requires_consent(svc):
    out = svc.register(
        "s1",
        "0912345678",
        "小明",
        order_history_consent=False,
        personalization_consent=True,
    )
    assert out == {"ok": False, "error": "consent_required"}
    assert svc.member_repository.get_member("0912345678") is None


def test_clear_session(svc):
    svc.register("s1", "0912345678", "小明")
    svc.clear_session("s1")
    assert svc.get_session_member("s1") is None
