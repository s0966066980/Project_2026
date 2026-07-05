import importlib
import json


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "category": "超值全餐", "price": 155},
    {"id": "MCD012", "name": "薯條(中)", "category": "點心", "price": 45},
]


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
        "required_cart_item_ids": ["MCD012"],
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
    assert saved["metadata"]["status"] == "active"
    assert service.list_promotions()[0]["offer_id"] == "summer_combo_2026"


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
        "item_ids": ["MCD012"],
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
        "item_ids": ["MCD012"],
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
