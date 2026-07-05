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


def test_ai_push_guard_disallows_promotion_terms_without_offer():
    from services import rag_guard_service
    importlib.reload(rag_guard_service)

    section = rag_guard_service.build_ai_push_guard_section(
        item_id="MCD001",
        category="超值全餐",
        offers=[],
        audience="guest",
    )

    assert "沒有已驗證活動" in section
    assert "不得出現優惠" in section


def test_sanitize_unverified_promotion_claims_replaces_fake_discount():
    from services import rag_guard_service
    importlib.reload(rag_guard_service)

    text = rag_guard_service.sanitize_unverified_promotion_claims(
        "大麥克套餐限時優惠買一送一",
        "大麥克套餐",
        has_verified_offer=False,
    )

    assert text == "大麥克套餐現在很適合來一份，搭配點餐剛剛好！"
