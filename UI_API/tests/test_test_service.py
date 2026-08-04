"""Admin LLM diagnostic: the Diagnostic Provider Override must reach the provider it names.

These tests exist because the override silently stopped working once: the Admin panel kept
sending `ollama` no matter which provider tab was active, so the NVIDIA NIM path was never
exercised while every assertion here still passed. The service-level tests below therefore
pin the provider that actually received the prompt, not just the label on the reply.
"""

import importlib

import pytest


def _reloaded_test_service():
    from services import test_service

    importlib.reload(test_service)
    return test_service


@pytest.fixture
def diagnostic_service(monkeypatch):
    service = _reloaded_test_service()
    monkeypatch.setattr(
        service,
        "_build_voice_user_prompt",
        lambda user_text, history: f"user:{user_text}",
    )
    monkeypatch.setattr(service, "_get_default_voice_prompt", lambda: "default-system")
    return service


class _FakeResponse:
    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def test_nvidia_nim_override_calls_nvidia_with_the_named_model(diagnostic_service, monkeypatch):
    import requests

    import config

    called = {}

    def fake_post(url, json, headers, timeout):
        called.update(url=url, model=json["model"], headers=headers, messages=json["messages"])
        return _FakeResponse('{"ai_response":"可以幫您推薦大麥克。","mentioned_ids":["MCD001"]}')

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(config, "NVIDIA_API_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "test-key")

    result = diagnostic_service.ask_voice_style(
        "nvidia_nim", "meta/llama-3.1-70b-instruct", "system", "有什麼推薦", [],
    )

    assert called["url"] == "https://example.test/v1/chat/completions"
    assert called["model"] == "meta/llama-3.1-70b-instruct"
    assert called["headers"]["Authorization"] == "Bearer test-key"
    assert result["provider"] == "nvidia_nim"
    assert result["model"] == "meta/llama-3.1-70b-instruct"
    assert result["ai_response"] == "可以幫您推薦大麥克。"
    assert result["mentioned_ids"] == ["MCD001"]


def test_ollama_override_never_reaches_the_cloud_provider(diagnostic_service, monkeypatch):
    import ai_services
    import requests

    def forbidden_post(*args, **kwargs):  # pragma: no cover - only runs on regression
        raise AssertionError("ollama 診斷不得送出雲端請求")

    monkeypatch.setattr(requests, "post", forbidden_post)
    monkeypatch.setattr(
        ai_services,
        "ask_ollama",
        lambda system_prompt, user_prompt, response_tag="", model_name="", num_predict=None: {
            "ai_response": "本機回覆", "model": model_name,
        },
    )

    result = diagnostic_service.ask_voice_style("ollama", "qwen3.5:4b", "system", "hello", [])

    assert result["provider"] == "ollama"
    assert result["model"] == "qwen3.5:4b"
    assert result["ai_response"] == "本機回覆"


def test_missing_nvidia_credential_is_reported_without_sending_a_request(diagnostic_service, monkeypatch):
    """The acceptance signal for a working override: only the NIM path can produce this."""

    import requests

    import config

    def forbidden_post(*args, **kwargs):  # pragma: no cover - only runs on regression
        raise AssertionError("缺少金鑰時不得送出請求")

    monkeypatch.setattr(requests, "post", forbidden_post)
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")

    result = diagnostic_service.ask_voice_style("nvidia_nim", "", "system", "hello", [])

    assert result["provider"] == "nvidia_nim"
    assert result["error"] == "缺少 API 金鑰，未送出請求。"
    assert result["latency_ms"] == 0


def test_unparseable_reply_surfaces_the_raw_body_as_the_finding(diagnostic_service, monkeypatch):
    import requests

    import config

    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse("純文字回覆"))
    monkeypatch.setattr(config, "NVIDIA_API_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "test-key")

    result = diagnostic_service.ask_voice_style("nvidia_nim", "", "system", "hello", [])

    assert result["provider"] == "nvidia_nim"
    assert "回應格式無法解析。" in result["error"]
    assert "純文字回覆" in result["error"]


def test_unknown_provider_is_rejected_rather_than_run_locally(diagnostic_service):
    result = diagnostic_service.ask_voice_style("ollma", "", "system", "hello", [])

    assert "ollma" in result["error"]
    assert "ai_response" not in result


def test_supported_providers_are_exactly_the_two_halves_of_the_chain(diagnostic_service):
    assert diagnostic_service.SUPPORTED_TEST_PROVIDERS == frozenset({"ollama", "nvidia_nim"})


def _diagnostic_client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tests.auth_test_support import authenticate_client, configure_admin_session

    from routes import test_routes

    app = FastAPI()
    app.include_router(test_routes.create_router({}))
    client = TestClient(app)
    configure_admin_session(monkeypatch)
    authenticate_client(client)
    return client


@pytest.mark.parametrize(
    "body",
    [
        {"messages": [{"role": "user", "content": "hi"}]},          # provider 未送出
        {"provider": "", "messages": []},                            # 空字串
        {"provider": "ollma", "messages": []},                       # 拼錯
        {"provider": "openai", "messages": []},                      # 不在鏈上的提供者
    ],
)
def test_diagnostic_rejects_any_provider_it_cannot_name(monkeypatch, body):
    """A missing provider is a caller error, not a cue to quietly run the local runtime."""

    from services import test_service

    def forbidden(*args, **kwargs):  # pragma: no cover - only runs on regression
        raise AssertionError("不合法的 provider 不得送出任何提示詞")

    monkeypatch.setattr(test_service, "ask_voice_style", forbidden)
    client = _diagnostic_client(monkeypatch)

    response = client.post("/api/test/ask", json=body)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "nvidia_nim" in detail and "ollama" in detail


def test_diagnostic_forwards_a_supported_provider_verbatim(monkeypatch):
    from services import test_service

    seen = {}

    def fake_ask(provider, model, system_prompt, user_text, history):
        seen.update(provider=provider, model=model, user_text=user_text, history=history)
        return {"ai_response": "ok", "provider": provider, "model": model, "latency_ms": 1}

    monkeypatch.setattr(test_service, "ask_voice_style", fake_ask)
    client = _diagnostic_client(monkeypatch)

    response = client.post("/api/test/ask", json={
        "provider": "nvidia_nim",
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "user", "content": "第一輪"},
            {"role": "assistant", "content": "回覆"},
            {"role": "user", "content": "第二輪"},
        ],
    })

    assert response.status_code == 200
    assert seen["provider"] == "nvidia_nim"
    assert seen["model"] == "meta/llama-3.1-70b-instruct"
    assert seen["user_text"] == "第二輪"
    assert len(seen["history"]) == 2
    assert response.json()["provider"] == "nvidia_nim"
