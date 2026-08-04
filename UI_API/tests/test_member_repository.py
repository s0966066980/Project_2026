import importlib

import pytest


@pytest.fixture
def repo(tmp_path, monkeypatch):
    from repositories import member_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    return member_repository


def _rec(phone, nickname="x"):
    return {"phone": phone, "nickname": nickname, "visit_count": 0, "item_freq": {}, "orders": []}


def test_missing_file_returns_empty(repo):
    assert repo.get_all_members() == []
    assert repo.get_member("0912345678") is None


def test_upsert_then_get(repo):
    repo.upsert_member(_rec("0912345678", "小明"))
    got = repo.get_member("0912345678")
    assert got["nickname"] == "小明"
    assert repo.get_all_members() and len(repo.get_all_members()) == 1


def test_upsert_replaces_same_phone(repo):
    repo.upsert_member(_rec("0912345678", "舊"))
    repo.upsert_member(_rec("0912345678", "新"))
    assert len(repo.get_all_members()) == 1
    assert repo.get_member("0912345678")["nickname"] == "新"


def test_upsert_appends_distinct_phone(repo):
    repo.upsert_member(_rec("0912345678"))
    repo.upsert_member(_rec("0928000000"))
    assert len(repo.get_all_members()) == 2
