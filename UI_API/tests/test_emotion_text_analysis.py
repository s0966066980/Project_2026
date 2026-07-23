import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.llm import LLMResponse


def _llm_response(*, parsed=None, safe_error="") -> LLMResponse:
    return LLMResponse(
        content="",
        provider="ollama",
        model="qwen-test",
        latency_ms=12.5,
        usage=None,
        finish_reason="stop",
        safe_error=safe_error,
        parsed=parsed,
        prompt_version="emotion_text-v1",
    )


def test_text_emotion_analysis_returns_structured_evidence_without_storing_raw_text(monkeypatch):
    from services import emotion_service

    captured = {}
    logs = []

    long_description = "顧客反覆詢問下一步並使用多個問號，顯示對點餐流程感到困惑與焦慮，需要簡短而明確的選項說明"

    def fake_generate(request):
        captured["request"] = request
        return _llm_response(parsed={
            "emotion": "anxiety",
            "intensity": "high",
            "confidence": 0.87,
            "answer": "判讀為高強度焦慮。",
            "description": long_description,
            "facial": "不應採用",
        })

    monkeypatch.setattr(emotion_service.llm_gateway_service, "generate", fake_generate)
    monkeypatch.setattr(emotion_service.emotion_log_repository, "append_log", lambda entry: logs.append(dict(entry)))
    monkeypatch.setattr(emotion_service.config, "get", lambda key, default=None: default)
    raw_text = "我已經試了很多次，為什麼還是不能付款？"

    result = asyncio.run(emotion_service.analyze_text(raw_text))

    assert result["status"] == "ok"
    assert result["emotion"] == "anxious"
    assert result["intensity"] == "high"
    assert result["confidence"] == 0.87
    assert result["provider"] == "text_llm"
    assert result["analysis_source"] == "text_emotion_model"
    assert result["analysis_source_label"] == "文字情緒分析模型"
    assert result["text_analysis_answer"] == "判讀為高強度焦慮。"
    assert result["description"] == long_description[:40]
    assert result["facial"] == ""
    assert result["vocal"] == ""
    assert result["decision_boundary"] == "evidence_only"
    assert result["input_character_count"] == len(raw_text)
    assert raw_text not in str(result)
    assert raw_text not in str(logs)
    assert captured["request"].task == "emotion_text_analysis"
    assert captured["request"].prompt_version == "emotion_text-v2"
    assert "餐飲自助點餐" in captured["request"].system_prompt
    assert "40" in captured["request"].system_prompt
    assert raw_text in captured["request"].user_prompt


def test_text_emotion_analysis_fails_safely_without_exposing_model_error(monkeypatch):
    from services import emotion_service

    logs = []
    monkeypatch.setattr(
        emotion_service.llm_gateway_service,
        "generate",
        lambda request: _llm_response(safe_error="private provider failure"),
    )
    monkeypatch.setattr(emotion_service.emotion_log_repository, "append_log", lambda entry: logs.append(dict(entry)))
    monkeypatch.setattr(emotion_service.config, "get", lambda key, default=None: default)

    result = asyncio.run(emotion_service.analyze_text("我不知道該怎麼辦"))

    assert result["status"] == "error"
    assert result["emotion"] == ""
    assert "private provider failure" not in str(result)
    assert logs[0]["evidence_quality"] == "error"


def test_admin_text_emotion_route_validates_input_and_permission(monkeypatch):
    from routes import emotion_routes

    calls = []
    permissions = []

    async def fake_analyze(text):
        calls.append(text)
        return {"status": "ok", "emotion": "confused", "decision_boundary": "evidence_only"}

    monkeypatch.setattr(emotion_routes.emotion_service, "analyze_text", fake_analyze)
    monkeypatch.setattr(
        emotion_routes,
        "authorize_admin_request",
        lambda request, permission: permissions.append(permission) or object(),
    )
    monkeypatch.setattr(emotion_routes, "check_rate_limit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(emotion_routes.create_router({}))
    client = TestClient(app)

    response = client.post("/api/emotion/analyze_text", json={"text": "  我看不懂下一步  "})

    assert response.status_code == 200
    assert response.json()["emotion"] == "confused"
    assert calls == ["我看不懂下一步"]
    assert permissions == ["system.debug"]
    assert client.post("/api/emotion/analyze_text", json={"text": "   "}).status_code == 422
    assert client.post("/api/emotion/analyze_text", json={"text": "x" * 501}).status_code == 422


def test_admin_media_emotion_route_disables_intervention_side_effects(monkeypatch):
    from routes import emotion_routes

    calls = []
    permissions = []

    async def fake_analyze_event(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "emotion": "happy", "test_mode": True}

    monkeypatch.setattr(emotion_routes.emotion_service, "analyze_event", fake_analyze_event)
    monkeypatch.setattr(
        emotion_routes,
        "authorize_admin_request",
        lambda request, permission: permissions.append(permission) or object(),
    )
    monkeypatch.setattr(emotion_routes, "check_rate_limit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(emotion_routes.create_router({}))
    client = TestClient(app)

    response = client.post(
        "/api/emotion/analyze_media_test",
        data={"speech_text": "測試說話"},
        files={"media": ("clip.webm", b"test-video", "video/webm")},
    )

    assert response.status_code == 200
    assert response.json()["test_mode"] is True
    assert permissions == ["system.debug"]
    assert calls[0]["event_type"] == "admin_media_test"
    assert calls[0]["speech_text"] == "測試說話"
    assert calls[0]["update_voice_session"] is False


def test_kiosk_emotion_route_only_accepts_voice_lifecycle_events(monkeypatch):
    from routes import emotion_routes

    calls = []

    async def fake_analyze_event(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "event_type": kwargs["event_type"]}

    monkeypatch.setattr(emotion_routes.emotion_service, "analyze_event", fake_analyze_event)
    monkeypatch.setattr(emotion_routes, "require_kiosk_token", lambda request: object())
    monkeypatch.setattr(emotion_routes, "check_rate_limit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(emotion_routes.create_router({}))
    client = TestClient(app)
    common = {
        "session_id": "kiosk-session",
        "emotion_round_id": "round-1",
        "voice_turn_id": "turn-2",
        "voice_turn_index": "2",
        "observed_at_ms": "1234",
    }

    response = client.post(
        "/api/emotion/analyze_event",
        data={**common, "event_type": "voice_mode_ended", "speech_text": "我想要一份大麥克"},
        files={"media": ("clip.webm", b"test-video", "video/webm")},
    )
    rejected = client.post(
        "/api/emotion/analyze_event",
        data={**common, "event_type": "payment_timeout"},
        files={"media": ("clip.webm", b"test-video", "video/webm")},
    )

    assert response.status_code == 200
    assert rejected.status_code == 422
    assert calls[0]["update_voice_session"] is True
    assert calls[0]["emotion_round_id"] == "round-1"
    assert calls[0]["voice_turn_id"] == "turn-2"
    assert calls[0]["voice_turn_index"] == 2
    assert calls[0]["observed_at_ms"] == 1234
    assert calls[0]["speech_text"] == "我想要一份大麥克"
