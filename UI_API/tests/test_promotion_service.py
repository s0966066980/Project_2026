import importlib
import json
from pathlib import Path


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "category": "超值全餐", "price": 155},
    {"id": "MCD115", "name": "薯條", "category": "點心", "price": 45},
]


def test_default_catalog_does_not_ship_retired_summer_promotions(monkeypatch):
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from repositories import promotion_repository

    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(promotion_repository.config, "RAG_DOCUMENTS_DIR", str(project_root / "rag_documents"))
    monkeypatch.setattr(promotion_repository.postgres_utils, "use_postgres", lambda: False)

    offer_ids = {
        str(row.get("offer_id") or row.get("id") or "")
        for row in promotion_repository.list_promotions_scoped(LEGACY_DEFAULT_SCOPE)
    }

    assert offer_ids.isdisjoint({"summer_drink", "summer_food"})


def _setup_service(tmp_path, monkeypatch):
    from services import promotion_service

    importlib.reload(promotion_service)
    monkeypatch.setattr(promotion_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    monkeypatch.setattr(promotion_service.menu_repository, "get_menu", lambda: list(MENU))
    return promotion_service


def test_save_promotion_writes_validated_json(tmp_path, monkeypatch):
    service = _setup_service(tmp_path, monkeypatch)

    record, errors = service.save_promotion({
        "offer_id": "summer_combo_2026",
        "title": "夏季套餐推薦",
        "status": "active",
        "valid_from": "2026-07-01",
        "valid_until": "2026-07-31",
        "member_only": False,
        "item_ids": ["MCD001"],
        "categories": ["超值全餐"],
        "required_cart_item_ids": ["MCD115"],
        "pricing": {
            "type": "add_on_fixed_price",
            "original_price": 45,
            "promotion_price": 30,
            "currency": "TWD",
        },
        "ad": {
            "headline": "會員限定",
            "copy": "主餐加購薯條只要 $30",
            "cta": "加入優惠",
        },
        "score_boost": 5,
        "category_score_boost": 3,
        "content": "活動期間推薦指定套餐。",
    })

    assert errors == []
    assert record["offer_id"] == "summer_combo_2026"
    assert record["source_id"] == "promotion_summer_combo_2026"
    assert record["timezone"] == "Asia/Taipei"
    path = tmp_path / "rag_documents" / "promotions" / "summer_combo_2026.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["status"] == "active"
    assert saved["timezone"] == "Asia/Taipei"
    assert saved["pricing"]["promotion_price"] == 30
    assert saved["ad"]["copy"] == "主餐加購薯條只要 $30"
    assert saved["surface"] == "recommendation"
    assert saved["enabled"] is True
    assert saved["metadata"]["status"] == "active"
    assert service.list_promotions()[0]["offer_id"] == "summer_combo_2026"


def test_save_pos_banner_allows_target_without_item_scope(tmp_path, monkeypatch):
    service = _setup_service(tmp_path, monkeypatch)

    record, errors = service.save_promotion({
        "offer_id": "summer_banner_2026",
        "title": "夏日超值套餐",
        "status": "active",
        "surface": "pos_home_banner",
        "priority": 100,
        "badge": "限時優惠",
        "subtitle": "雙層牛肉吉士堡 + 中薯 + 中可",
        "start_at": "2026-07-01T00:00:00+08:00",
        "end_at": "2026-07-31T23:59:59+08:00",
        "original_price": 189,
        "promo_price": 149,
        "save_text": "現省 $40",
        "target_type": "category",
        "target_value": "超值全餐",
        "theme": "gold",
    })

    assert errors == []
    assert record["surface"] == "pos_home_banner"
    assert record["promo_price"] == 149
    assert record["pricing"]["promotion_price"] == 149
    assert record["target_value"] == "超值全餐"


def test_save_promotion_rejects_end_before_start(tmp_path, monkeypatch):
    service = _setup_service(tmp_path, monkeypatch)

    record, errors = service.save_promotion({
        "offer_id": "bad_dates",
        "title": "錯誤日期",
        "status": "active",
        "surface": "pos_home_banner",
        "start_at": "2026-07-31T23:59:59+08:00",
        "end_at": "2026-07-01T00:00:00+08:00",
        "target_type": "none",
    })

    assert record is None
    assert any("end_at 不可早於 start_at" in error for error in errors)


def test_save_promotion_rejects_invalid_targets(tmp_path, monkeypatch):
    service = _setup_service(tmp_path, monkeypatch)

    record, errors = service.save_promotion({
        "offer_id": "bad_offer",
        "title": "錯誤活動",
        "status": "active",
        "item_ids": ["NOT_IN_MENU"],
    })

    assert record is None
    assert any("item_ids 不存在" in error for error in errors)
    assert any("至少需要一個有效" in error for error in errors)


def test_save_promotion_rejects_invalid_timezone(tmp_path, monkeypatch):
    service = _setup_service(tmp_path, monkeypatch)

    record, errors = service.save_promotion({
        "offer_id": "bad_timezone",
        "title": "錯誤時區活動",
        "status": "active",
        "timezone": "Mars/Olympus",
        "item_ids": ["MCD001"],
    })

    assert record is None
    assert any("timezone 不存在" in error for error in errors)


def test_update_status_and_delete_promotion(tmp_path, monkeypatch):
    service = _setup_service(tmp_path, monkeypatch)
    record, errors = service.save_promotion({
        "offer_id": "member_fries",
        "title": "會員薯條活動",
        "status": "draft",
        "member_only": True,
        "item_ids": ["MCD115"],
    })
    assert errors == []

    updated, errors = service.update_promotion_status("member_fries", "active")
    assert errors == []
    assert updated["status"] == "active"
    assert service.get_promotion("member_fries")["metadata"]["status"] == "active"

    assert service.delete_promotion("member_fries") is True
    assert service.get_promotion("member_fries") is None


def test_update_status_handles_legacy_filename_that_differs_from_offer_id(tmp_path, monkeypatch):
    service = _setup_service(tmp_path, monkeypatch)
    promotions_root = tmp_path / "rag_documents" / "promotions"
    promotions_root.mkdir(parents=True)
    legacy_path = promotions_root / "example-member-offer.json"
    legacy_path.write_text(json.dumps([{
        "type": "promotion",
        "offer_id": "example_member_fries",
        "source_id": "promotion_example_member_fries",
        "source_type": "promotion",
        "title": "會員薯條加購示例",
        "status": "draft",
        "timezone": "Asia/Taipei",
        "member_only": True,
        "item_ids": ["MCD115"],
        "categories": ["點心"],
        "metadata": {"status": "draft"},
    }], ensure_ascii=False), encoding="utf-8")

    listed = service.list_promotions()
    assert listed[0]["offer_id"] == "example_member_fries"
    assert listed[0]["path"] == "example-member-offer.json"

    updated, errors = service.update_promotion_status("example_member_fries", "active")

    assert errors == []
    assert updated["status"] == "active"
    assert updated["path"] == "example-member-offer.json"
    assert legacy_path.exists()
    saved = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert saved["status"] == "active"
    assert saved["metadata"]["status"] == "active"
    assert service.delete_promotion("example_member_fries") is True
    assert not legacy_path.exists()
