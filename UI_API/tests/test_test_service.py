import importlib


def test_openai_provider_uses_openai_chat_completion(monkeypatch):
    from services import test_service
    importlib.reload(test_service)

    called = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": '{"ai_response":"可以幫您推薦大麥克。","mentioned_ids":["MCD001"],"cart_actions":[]}'
                    }
                }]
            }

    def fake_post(url, json, headers, timeout):
        called["url"] = url
        called["model"] = json["model"]
        called["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(test_service.requests, "post", fake_post)
    monkeypatch.setattr(
        test_service.config,
        "get",
        lambda key, default=None: {
            "OPENAI_API_BASE_URL": "https://example.test/v1",
            "OPENAI_API_KEY": "test-key",
            "VOICE_ASSIST_SYSTEM_PROMPT": "system",
        }.get(key, default),
    )

    result = test_service.ask_voice_style(
        "openai",
        "gpt-test",
        "system",
        "有什麼推薦",
        [],
    )

    assert called["url"] == "https://example.test/v1/chat/completions"
    assert called["model"] == "gpt-test"
    assert called["headers"]["Authorization"] == "Bearer test-key"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-test"
    assert result["ai_response"] == "可以幫您推薦大麥克。"
    assert result["mentioned_ids"] == ["MCD001"]


def test_openai_provider_returns_text_when_response_is_not_json(monkeypatch):
    from services import test_service
    importlib.reload(test_service)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "純文字回覆"}}]}

    monkeypatch.setattr(test_service.requests, "post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(test_service.config, "get", lambda key, default=None: default)

    result = test_service.ask_voice_style("openai", "", "system", "hello", [])

    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-mini"
    assert result["text"] == "純文字回覆"
