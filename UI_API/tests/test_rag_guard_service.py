import importlib


def test_voice_guard_blocks_unverified_guest_promotion_claims():
    from services import rag_guard_service
    importlib.reload(rag_guard_service)

    section = rag_guard_service.build_voice_guard_section(
        "今天有什麼優惠？",
        offers=[{
            "title": "會員薯條活動",
            "member_only": True,
            "item_ids": ["MCD012"],
        }],
        audience="guest",
    )

    assert "沒有可對該受眾確認" in section
    assert "不得編造折扣或活動" in section


def test_voice_guard_allows_visible_verified_offer():
    from services import rag_guard_service
    importlib.reload(rag_guard_service)

    section = rag_guard_service.build_voice_guard_section(
        "會員優惠有哪些？",
        offers=[{
            "title": "會員薯條活動",
            "member_only": True,
            "item_ids": ["MCD012"],
        }],
        audience="member",
    )

    assert "只能使用【已驗證 RAG 優惠】" in section
    assert "不得自行補充" in section


def test_offers_targeting_item_ignores_offers_for_other_items():
    from services import rag_guard_service
    importlib.reload(rag_guard_service)

    offers = [
        {"offer_id": "off_1", "title": "早餐買一送一", "item_ids": ["MCD001"]},
        {"offer_id": "off_2", "title": "飲料半價", "categories": ["飲料"]},
    ]

    matched = rag_guard_service.offers_targeting_item(
        "MCD001",
        category="超值全餐",
        offers=offers,
        audience="guest",
    )

    assert [row["offer_id"] for row in matched] == ["off_1"]


def test_offers_targeting_item_hides_member_only_offer_from_guest():
    from services import rag_guard_service
    importlib.reload(rag_guard_service)

    offers = [{"offer_id": "off_m", "title": "會員價", "item_ids": ["MCD001"], "member_only": True}]

    assert rag_guard_service.offers_targeting_item("MCD001", offers=offers, audience="guest") == []
    assert len(rag_guard_service.offers_targeting_item("MCD001", offers=offers, audience="member")) == 1


def test_unverified_promotion_terms_flags_authored_discount_claim():
    from services import rag_guard_service
    importlib.reload(rag_guard_service)

    # Authored base copy is shown to every customer until edited, so a promotional claim is
    # reported for rejection at save time rather than rewritten when it is served.
    assert rag_guard_service.unverified_promotion_terms("大麥克套餐限時優惠買一送一") == [
        "優惠",
        "買一送一",
        "限時優惠",
    ]


def test_unverified_promotion_terms_allows_plain_food_description():
    from services import rag_guard_service
    importlib.reload(rag_guard_service)

    assert rag_guard_service.unverified_promotion_terms("雙層牛肉與招牌醬，份量十足一次滿足。") == []
