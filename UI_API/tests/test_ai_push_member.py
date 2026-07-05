import importlib
import asyncio


class FakeSemaphore:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


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


def test_generate_push_text_sanitizes_unverified_discount(monkeypatch):
    from services import ai_push_service
    importlib.reload(ai_push_service)

    monkeypatch.setattr(
        ai_push_service.ai_services,
        "ask_ollama",
        lambda *args, **kwargs: {"push_text": "大麥克套餐限時優惠買一送一，現在最划算"},
    )

    def fake_config_get(key, default=None):
        values = {
            "AI_PUSH_SYSTEM_PROMPT": "system",
            "AI_PUSH_TEXT_MIN": 18,
            "AI_PUSH_TEXT_MAX": 34,
            "OLLAMA_NUM_PREDICT": 220,
            "MODEL_NAME": "model",
        }
        return values.get(key, default)

    monkeypatch.setattr(ai_push_service.config, "get", fake_config_get)
    context = {
        "audience": "guest",
        "rag": {"context": "", "offers": []},
        "menu_items": [{"id": "MCD001", "name": "大麥克套餐", "category": "超值全餐"}],
    }

    push_text, status = asyncio.run(
        ai_push_service._generate_push_text(
            context,
            "MCD001",
            "大麥克套餐",
            FakeSemaphore(),
        )
    )

    assert status == "success"
    assert push_text == "大麥克套餐現在很適合來一份，搭配點餐剛剛好！"
    assert "優惠" not in push_text
    assert "買一送一" not in push_text


def test_generate_push_text_keeps_verified_offer_text(monkeypatch):
    from services import ai_push_service
    importlib.reload(ai_push_service)

    monkeypatch.setattr(
        ai_push_service.ai_services,
        "ask_ollama",
        lambda *args, **kwargs: {"push_text": "會員薯條活動開跑，大麥克套餐搭配點心更滿足"},
    )
    monkeypatch.setattr(
        ai_push_service.config,
        "get",
        lambda key, default=None: {
            "AI_PUSH_SYSTEM_PROMPT": "system",
            "AI_PUSH_TEXT_MIN": 18,
            "AI_PUSH_TEXT_MAX": 34,
            "OLLAMA_NUM_PREDICT": 220,
            "MODEL_NAME": "model",
        }.get(key, default),
    )
    context = {
        "audience": "member",
        "rag": {
            "context": "",
            "offers": [{
                "title": "會員薯條活動",
                "member_only": True,
                "categories": ["超值全餐"],
            }],
        },
        "menu_items": [{"id": "MCD001", "name": "大麥克套餐", "category": "超值全餐"}],
    }

    push_text, status = asyncio.run(
        ai_push_service._generate_push_text(
            context,
            "MCD001",
            "大麥克套餐",
            FakeSemaphore(),
        )
    )

    assert status == "success"
    assert "會員薯條活動" in push_text
