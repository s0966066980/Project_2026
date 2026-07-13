import importlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo


def _setup(tmp_path, monkeypatch):
    from services import promotion_banner_service

    importlib.reload(promotion_banner_service)
    monkeypatch.setattr(promotion_banner_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    return promotion_banner_service


def _write_promotion(tmp_path, name, data):
    root = tmp_path / "rag_documents" / "promotions"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _now():
    return datetime(2026, 7, 6, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))


def _banner(**overrides):
    row = {
        "id": "summer_combo_001",
        "offer_id": "summer_combo_001",
        "enabled": True,
        "surface": "pos_home_banner",
        "priority": 100,
        "rotation_seconds": 8,
        "status": "active",
        "badge": "限時優惠",
        "title": "夏日超值套餐",
        "subtitle": "雙層牛肉吉士堡 + 中薯 + 中可",
        "original_price": 189,
        "promo_price": 149,
        "save_text": "現省 $40",
        "start_at": "2026-07-01T00:00:00+08:00",
        "end_at": "2026-07-31T23:59:59+08:00",
        "cta_text": "立即查看",
        "target_type": "category",
        "target_value": "超值全餐",
        "theme": "gold",
        "legal_text": "活動依門市供應狀態為準",
        "item_ids": ["MCD115"],
        "categories": ["點心"],
        "required_cart_item_ids": ["MCD001"],
    }
    row.update(overrides)
    return row


def test_active_pos_banner_is_returned(tmp_path, monkeypatch):
    service = _setup(tmp_path, monkeypatch)
    _write_promotion(tmp_path, "active", _banner())

    items = service.get_active_pos_banners(now=_now())

    assert len(items) == 1
    assert items[0]["id"] == "summer_combo_001"
    assert items[0]["promo_price"] == 149
    assert items[0]["rotation_seconds"] == 8
    assert items[0]["item_ids"] == ["MCD115"]
    assert items[0]["categories"] == ["點心"]
    assert items[0]["required_cart_item_ids"] == ["MCD001"]


def test_expired_pos_banner_is_filtered(tmp_path, monkeypatch):
    service = _setup(tmp_path, monkeypatch)
    _write_promotion(tmp_path, "expired", _banner(end_at="2026-06-30T23:59:59+08:00"))

    assert service.get_active_pos_banners(now=_now()) == []


def test_disabled_pos_banner_is_filtered(tmp_path, monkeypatch):
    service = _setup(tmp_path, monkeypatch)
    _write_promotion(tmp_path, "disabled", _banner(enabled=False))
    _write_promotion(tmp_path, "inactive", _banner(id="inactive", offer_id="inactive", status="inactive"))

    assert service.get_active_pos_banners(now=_now()) == []


def test_priority_sorts_highest_first(tmp_path, monkeypatch):
    service = _setup(tmp_path, monkeypatch)
    _write_promotion(tmp_path, "low", _banner(id="low", offer_id="low", priority=10, title="低優先級"))
    _write_promotion(tmp_path, "high", _banner(id="high", offer_id="high", priority=200, title="高優先級"))

    items = service.get_active_pos_banners(now=_now())

    assert [item["id"] for item in items] == ["high", "low"]


def test_no_pos_banner_returns_empty_response(tmp_path, monkeypatch):
    service = _setup(tmp_path, monkeypatch)

    assert service.get_pos_banner_response(now=_now()) == {"items": []}


def test_cart_banner_surface_filters_separately(tmp_path, monkeypatch):
    service = _setup(tmp_path, monkeypatch)
    _write_promotion(tmp_path, "home", _banner(id="home", offer_id="home", surface="pos_home_banner", title="首頁"))
    _write_promotion(tmp_path, "cart", _banner(id="cart", offer_id="cart", surface="kiosk_cart_banner", title="購物車"))

    payload = service.get_pos_banner_response(now=_now(), surface="kiosk_cart_banner")

    assert [item["id"] for item in payload["items"]] == ["cart"]
