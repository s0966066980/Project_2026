import importlib
import json
from datetime import datetime, timezone


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐"},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
]


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_load_active_offers_filters_and_validates_menu_targets(tmp_path, monkeypatch):
    from services import rag_offer_service
    importlib.reload(rag_offer_service)

    monkeypatch.setattr(rag_offer_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path))

    def fake_config_get(key, default=None):
        values = {
            "RAG_ENABLED": True,
            "RECOMMENDATION_RAG_OFFER_WEIGHT": 7,
            "RECOMMENDATION_RAG_CATEGORY_WEIGHT": 3,
            "PROMOTION_DEFAULT_TIMEZONE": "Asia/Taipei",
        }
        return values.get(key, default)

    monkeypatch.setattr(rag_offer_service.config, "get", fake_config_get)
    _write_json(tmp_path / "promotions" / "offers.json", [
        {
            "offer_id": "member_fries",
            "title": "會員薯條活動",
            "member_only": True,
            "item_ids": ["MCD012", "NOT_IN_MENU"],
            "score_boost": 8,
            "valid_from": "2026-07-01",
            "valid_until": "2026-07-31",
            "timezone": "Asia/Taipei",
        },
        {
            "offer_id": "ignored_example",
            "title": "示例活動",
            "status": "example",
            "item_ids": ["MCD001"],
        },
        {
            "offer_id": "ignored_invalid_target",
            "title": "無效商品",
            "item_ids": ["NOT_IN_MENU"],
        },
    ])

    offers = rag_offer_service.load_active_offers(
        MENU,
        now=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )

    assert len(offers) == 1
    assert offers[0]["offer_id"] == "member_fries"
    assert offers[0]["item_ids"] == ["MCD012"]
    assert offers[0]["member_only"] is True
    assert offers[0]["score_boost"] == 8
    assert offers[0]["timezone"] == "Asia/Taipei"


def test_date_only_promotion_uses_local_timezone_until_end_of_day(tmp_path, monkeypatch):
    from services import rag_offer_service
    importlib.reload(rag_offer_service)

    monkeypatch.setattr(rag_offer_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path))

    def fake_config_get(key, default=None):
        values = {
            "RAG_ENABLED": True,
            "PROMOTION_DEFAULT_TIMEZONE": "Asia/Taipei",
            "RECOMMENDATION_RAG_OFFER_WEIGHT": 4,
            "RECOMMENDATION_RAG_CATEGORY_WEIGHT": 2,
        }
        return values.get(key, default)

    monkeypatch.setattr(rag_offer_service.config, "get", fake_config_get)
    _write_json(tmp_path / "promotions" / "taipei_dates.json", {
        "offer_id": "taipei_day_offer",
        "title": "台北整日活動",
        "status": "active",
        "item_ids": ["MCD001"],
        "valid_from": "2026-07-31",
        "valid_until": "2026-07-31",
        "timezone": "Asia/Taipei",
    })

    still_active = rag_offer_service.load_active_offers(
        MENU,
        now=datetime(2026, 7, 31, 15, 59, tzinfo=timezone.utc),
    )
    expired = rag_offer_service.load_active_offers(
        MENU,
        now=datetime(2026, 7, 31, 16, 1, tzinfo=timezone.utc),
    )

    assert [offer["offer_id"] for offer in still_active] == ["taipei_day_offer"]
    assert expired == []


def test_format_offer_prompt_section_hides_member_only_offer_for_guest():
    from services import rag_offer_service
    importlib.reload(rag_offer_service)

    offers = [{
        "title": "會員薯條活動",
        "member_only": True,
        "item_ids": ["MCD012"],
    }]

    assert rag_offer_service.format_offer_prompt_section(offers, audience="guest") == ""
    section = rag_offer_service.format_offer_prompt_section(offers, audience="member")
    assert "已驗證 RAG 優惠" in section
    assert "會員薯條活動" in section
    assert "不可自行編造" in section
