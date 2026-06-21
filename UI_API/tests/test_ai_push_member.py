import importlib


def test_weighted_pick_boosts_member_items(monkeypatch):
    from services import ai_push_service
    importlib.reload(ai_push_service)
    monkeypatch.setattr(ai_push_service, "get_top_items", lambda n=3: [])
    monkeypatch.setattr(ai_push_service.config, "get", lambda k, d=None: 50 if k == "MEMBER_PUSH_WEIGHT" else d)
    items = [{"id": "MCD001", "price": 100}, {"id": "MCD012", "price": 50}]
    # 會員常點 MCD012，權重 50 倍 → 100 次抽樣應壓倒性命中 MCD012
    hits = [ai_push_service._weighted_pick(items, set(), 3, ["MCD012"])["id"] for _ in range(100)]
    assert hits.count("MCD012") > 90


def test_weighted_pick_no_member_unchanged(monkeypatch):
    from services import ai_push_service
    importlib.reload(ai_push_service)
    monkeypatch.setattr(ai_push_service, "get_top_items", lambda n=3: [])
    items = [{"id": "MCD001", "price": 100}]
    assert ai_push_service._weighted_pick(items, set(), 3, None)["id"] == "MCD001"
