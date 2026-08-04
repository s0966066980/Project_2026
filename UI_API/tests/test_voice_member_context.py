import asyncio
import importlib

import pytest


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐"},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
]


@pytest.fixture
def voice_stack(tmp_path, monkeypatch):
    from repositories import member_repository, menu_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    monkeypatch.setattr(menu_repository, "get_menu", lambda: list(MENU))

    from services import member_service, member_preference_service, recommendation_context_service, voice_service
    importlib.reload(member_service)
    importlib.reload(member_preference_service)
    importlib.reload(recommendation_context_service)
    importlib.reload(voice_service)

    member_service._session_member.clear()
    monkeypatch.setattr(member_service.menu_repository, "get_menu", lambda: list(MENU))
    monkeypatch.setattr(recommendation_context_service, "get_top_items", lambda n=3: [MENU[1]])
    monkeypatch.setattr(voice_service.session_repository, "get_session_history", lambda session_id: [])

    async def fake_load_menu_cached():
        return list(MENU), "【菜單】\nMCD001｜大麥克套餐\nMCD012｜薯條(中)"

    monkeypatch.setattr(voice_service, "_load_menu_cached", fake_load_menu_cached)

    def fake_config_get(key, default=None):
        values = {
            "RAG_ENABLED": False,
            "EMOTION_LLAMA_AFFECT_VOICE": False,
            "VOICE_ASSIST_SYSTEM_PROMPT": "system",
            "VOICE_HISTORY_MAX_TURNS": 4,
            "AI_PUSH_PRIORITY_CATS": [],
        }
        return values.get(key, default)

    monkeypatch.setattr(voice_service.config, "get", fake_config_get)
    return voice_service, member_service


def test_voice_context_includes_member_preference_section(voice_stack):
    voice_service, member_service = voice_stack
    member_service.register("s1", "0912345678", "小明")
    member = member_service.member_repository.get_member("0912345678")
    member["item_freq"] = {"MCD001": 4}
    member["orders"] = [{"cart_ids": ["MCD001", "MCD012"], "order_status": "completed"}]
    member_service.member_repository.upsert_member(member)

    _, prompt, _ = asyncio.run(voice_service._build_voice_context("s1", "有什麼推薦"))
    assert "會員偏好摘要" in prompt
    assert "會員常點 ID" in prompt
    assert "MCD001｜大麥克套餐｜超值全餐｜常點 4 次" in prompt
    assert "最近完成訂單 ID" in prompt
    assert "MCD012｜薯條(中)｜點心" in prompt
    assert "取得明確確認後才輸出 cart_actions" in prompt
    assert "小明" in prompt
    assert "大麥克套餐" in prompt
    assert "0912345678" not in prompt


def test_voice_context_omits_member_section_for_guest(voice_stack):
    voice_service, _ = voice_stack
    _, prompt, _ = asyncio.run(voice_service._build_voice_context("guest", "有什麼推薦"))
    assert "會員偏好摘要" not in prompt


def test_voice_context_includes_rag_guard_for_promotion_question(voice_stack):
    voice_service, _ = voice_stack

    _, prompt, _ = asyncio.run(voice_service._build_voice_context("guest", "今天有什麼優惠"))

    assert "RAG 回答防編造規則" in prompt
    assert "目前沒有可對該受眾確認的已驗證活動" in prompt
    assert "不得編造折扣或活動" in prompt
