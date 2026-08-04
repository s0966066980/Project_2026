"""Milestone 5D: emotion production path uses Multimodal Evidence Gateway."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.multimodal_evidence import MultimodalEvidence, MultimodalEvidenceRequest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
SERVICES = BACKEND / "services"


def test_emotion_service_does_not_import_httpx_or_call_predict_directly() -> None:
    source = (SERVICES / "emotion_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports_httpx = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "httpx":
                    imports_httpx = True
        if isinstance(node, ast.ImportFrom) and node.module == "httpx":
            imports_httpx = True
    assert imports_httpx is False
    assert "/predict" not in source
    assert "multimodal_evidence_gateway" in source


def test_only_gateway_adapters_hold_provider_http() -> None:
    gateway = (SERVICES / "multimodal_evidence_gateway.py").read_text(encoding="utf-8")
    assert "import httpx" in gateway
    assert "/predict" in gateway
    assert "class EmotionLlamaAdapter" in gateway
    assert "class R1OmniAdapter" in gateway


def test_analyze_event_uses_gateway_and_survives_no_evidence(monkeypatch) -> None:
    from services import emotion_service

    def fake_collect(request: MultimodalEvidenceRequest, **kwargs):
        assert request.event_type == "voice_mode_started"
        assert request.session_ref == "sess-1"
        return MultimodalEvidence(
            provider="emotion_llama",
            model_version="v-test",
            timestamp="2026-07-14T00:00:00+00:00",
            confidence=None,
            signals={},
            quality="unavailable",
            latency_ms=3.0,
            safe_error="provider_timeout",
            has_evidence=False,
            status="no_evidence",
        )

    monkeypatch.setattr(emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(emotion_service.multimodal_evidence_gateway, "collect_evidence", fake_collect)
    monkeypatch.setattr(
        emotion_service.emotion_log_repository,
        "append_log",
        lambda entry: entry,
    )

    entry = asyncio.run(
        emotion_service.analyze_event(
            session_id="sess-1",
            media_path="/tmp/clip.webm",
            event_type="voice_mode_started",
            speech_text="",
        )
    )
    assert entry["status"] in {"error", "no_evidence"}
    assert entry["decision_boundary"] == "evidence_only"
    assert entry.get("emotion", "") == ""


def test_analyze_event_maps_gateway_signals(monkeypatch) -> None:
    from services import emotion_service

    captured = {}

    def fake_collect(request: MultimodalEvidenceRequest, **kwargs):
        captured["request"] = request
        return MultimodalEvidence(
            provider="r1_omni",
            model_version="r1",
            timestamp="2026-07-14T00:00:00+00:00",
            confidence=0.8,
            signals={
                "emotion": "frustrated",
                "intensity": "medium",
                "facial": "眉頭微皺",
                "vocal": "語氣急促",
                "description": "顧客反覆確認餐點內容並加快語速，呈現明顯焦慮與選擇壓力，建議回應時先簡短確認需求再提供選項",
            },
            quality="ok",
            latency_ms=12.0,
            has_evidence=True,
            status="ok",
        )

    monkeypatch.setattr(emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(emotion_service.multimodal_evidence_gateway, "collect_evidence", fake_collect)
    monkeypatch.setattr(emotion_service.emotion_log_repository, "append_log", lambda entry: entry)
    monkeypatch.setattr(emotion_service.config, "get", lambda key, default=None: {
        "EMOTION_LLAMA_PROMPT": "q {speech_text}",
        "EMOTION_LLAMA_QUALITY_CHECK": False,
        "EMOTION_LLAMA_CLIP_SEC": 2.0,
        "EMOTION_PROVIDER": "r1_omni",
        "EMOTION_LLAMA_TIMEOUT_SEC": 5,
    }.get(key, default))

    emotion_service.clear_voice_emotion_cache("s2")
    entry = asyncio.run(
        emotion_service.analyze_event(
            "s2",
            "/tmp/a.webm",
            "admin_media_test",
            "hello",
            update_voice_session=False,
            comparison_pair_id="pair-admin-1",
            analysis_variant="media_plus_stt",
        )
    )
    assert entry["emotion"] == "frustrated"
    assert entry["provider"] == "r1_omni"
    assert entry["confidence"] == 0.8
    assert entry["status"] == "ok"
    assert entry["test_mode"] is True
    assert entry["decision_boundary"] == "evidence_only"
    assert entry["description"] == "顧客反覆確認餐點內容並加快語速，呈現明顯焦慮與選擇壓力，建議回應時先簡短確認需求再提供選項"
    assert entry["description_character_count"] == len(entry["description"])
    assert entry["speech_text_provided"] is True
    assert entry["speech_text_character_count"] == len("hello")
    assert entry["speech_context_mode"] == "embedded_audio_and_text"
    assert entry["comparison_pair_id"] == "pair-admin-1"
    assert entry["analysis_variant"] == "media_plus_stt"
    assert "點餐情緒觀察器" in captured["request"].question
    assert "情緒與強度" in captured["request"].question
    assert "點餐需求或困難" in captured["request"].question
    assert "回應重點" in captured["request"].question
    assert "80" in captured["request"].question
    assert emotion_service.get_voice_emotion_cache("s2") is None


def test_voice_cache_is_round_scoped_and_ignores_older_completed_analysis(monkeypatch) -> None:
    from services import emotion_service, voice_service

    def fake_collect(request: MultimodalEvidenceRequest, **_kwargs):
        ending = request.event_type == "voice_mode_ended"
        return MultimodalEvidence(
            provider="r1_omni",
            model_version="r1-test",
            timestamp="2026-07-15T00:00:00+00:00",
            confidence=0.9,
            signals={
                "emotion": "anxious" if ending else "happy",
                "intensity": "high" if ending else "low",
                "facial": "眉頭緊皺" if ending else "微笑",
                "vocal": "語速偏快" if ending else "平穩",
                "description": "voice emotion evidence",
            },
            quality="ok",
            latency_ms=10.0,
            has_evidence=True,
            status="ok",
        )

    monkeypatch.setattr(emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(emotion_service.multimodal_evidence_gateway, "collect_evidence", fake_collect)
    monkeypatch.setattr(emotion_service.emotion_log_repository, "append_log", lambda entry: entry)
    monkeypatch.setattr(emotion_service.config, "get", lambda key, default=None: {
        "EMOTION_LLAMA_PROMPT": "分析 {speech_text}",
        "EMOTION_LLAMA_QUALITY_CHECK": False,
        "EMOTION_LLAMA_CLIP_SEC": 3.0,
        "EMOTION_PROVIDER": "r1_omni",
        "EMOTION_LLAMA_TIMEOUT_SEC": 5,
    }.get(key, default))

    emotion_service.clear_voice_emotion_cache("voice-session")
    newer = asyncio.run(emotion_service.analyze_event(
        "voice-session",
        "/tmp/end.webm",
        "voice_mode_ended",
        emotion_round_id="round-a",
        voice_turn_id="turn-1",
        voice_turn_index=1,
        observed_at_ms=2000,
    ))
    asyncio.run(emotion_service.analyze_event(
        "voice-session",
        "/tmp/start.webm",
        "voice_mode_started",
        emotion_round_id="round-a",
        voice_turn_id="turn-1",
        voice_turn_index=1,
        observed_at_ms=1000,
    ))

    cached = emotion_service.get_voice_emotion_cache("voice-session", "round-a")
    assert newer["emotion"] == "anxious"
    assert newer["description_character_count"] == len("voice emotion evidence")
    assert newer["speech_text_provided"] is False
    assert newer["speech_context_mode"] == "embedded_audio_only"
    assert cached is not None
    assert cached["emotion"] == "anxious"
    assert cached["event_type"] == "voice_mode_ended"
    assert cached["voice_turn_id"] == "turn-1"
    assert emotion_service.get_voice_emotion_cache("voice-session", "round-b") is None
    monkeypatch.setattr(
        voice_service.config,
        "get",
        lambda key, default=None: {
            "EMOTION_LLAMA_AFFECT_VOICE": True,
            "EMOTION_ASSISTANCE_MODE": "active",
            "EMOTION_ASSISTANCE_CONFIDENCE_THRESHOLD": 0.7,
            "EMOTION_ASSISTANCE_ROLLOUT_PERCENT": 100,
        }.get(key, default),
    )
    context = voice_service._build_emotion_context("voice-session", "round-a")
    assert "本輪回覆輔助政策" in context
    assert "不得診斷或提及顧客情緒" in context
    assert "anxious" not in context
    assert voice_service._build_emotion_context("voice-session", "round-b") == ""


def test_voice_stream_exposes_stt_before_building_llm_context() -> None:
    source = (SERVICES / "voice_service.py").read_text(encoding="utf-8")
    stream_start = source.index("async def handle_voice_stream")
    transcript_yield = source.index('"type": "transcript"', stream_start)
    background_observation = source.index("_schedule_voice_emotion_observation(", transcript_yield)
    context_build = source.index("await _build_voice_context", transcript_yield)

    assert transcript_yield < background_observation < context_build
    critical_path = source[transcript_yield:context_build]
    assert "await _analyze_current_voice_emotion_pair" not in critical_path


def test_voice_emotion_pair_uses_the_same_media_and_returns_stt_variant(monkeypatch) -> None:
    from services import voice_service

    calls = []

    async def fake_analyze_event(session_id, media_path, event_type, speech_text="", **kwargs):
        calls.append({
            "session_id": session_id,
            "media_path": media_path,
            "event_type": event_type,
            "speech_text": speech_text,
            **kwargs,
        })
        return {
            "status": "ok",
            "emotion": "anxious" if speech_text else "neutral",
            "intensity": "medium" if speech_text else "low",
            "analysis_variant": kwargs["analysis_variant"],
            "comparison_pair_id": kwargs["comparison_pair_id"],
            "voice_turn_id": kwargs["voice_turn_id"],
        }

    monkeypatch.setattr(voice_service.emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(voice_service.emotion_service, "analyze_event", fake_analyze_event)
    monkeypatch.setattr(voice_service.emotion_service, "clear_voice_emotion_cache", lambda *args: None)
    monkeypatch.setattr(voice_service.config, "get", lambda key, default=None: {
        "EMOTION_LLAMA_EVENT_VOICE": True,
        "EMOTION_LLAMA_INCLUDE_STT": True,
        "EMOTION_LLAMA_ANALYSIS_MODE": "paired",
        "EMOTION_LLAMA_AFFECT_VOICE": True,
    }.get(key, default))

    reference = asyncio.run(voice_service._analyze_current_voice_emotion_pair(
        session_id="voice-session",
        media_path="/tmp/same-turn.webm",
        speech_text="我不知道要選哪一個套餐",
        emotion_round_id="round-a",
        voice_turn_id="turn-1",
        voice_turn_index=1,
    ))

    assert len(calls) == 2
    assert {call["media_path"] for call in calls} == {"/tmp/same-turn.webm"}
    assert {call["analysis_variant"] for call in calls} == {"media_only", "media_plus_stt"}
    assert {call["speech_text"] for call in calls} == {"", "我不知道要選哪一個套餐"}
    assert len({call["comparison_pair_id"] for call in calls}) == 1
    assert all(call["cache_voice_observation"] is True for call in calls)
    assert reference["analysis_variant"] == "media_plus_stt"
    assert reference["emotion"] == "anxious"


def test_voice_emotion_single_modes_only_run_the_selected_variant(monkeypatch) -> None:
    from services import voice_service

    calls = []

    async def fake_analyze_event(session_id, media_path, event_type, speech_text="", **kwargs):
        calls.append({"speech_text": speech_text, **kwargs})
        return {
            "status": "ok",
            "emotion": "anxious" if speech_text else "neutral",
            "analysis_variant": kwargs["analysis_variant"],
        }

    settings = {
        "EMOTION_LLAMA_EVENT_VOICE": True,
        "EMOTION_LLAMA_INCLUDE_STT": True,
        "EMOTION_LLAMA_ANALYSIS_MODE": "media_only",
        "EMOTION_LLAMA_AFFECT_VOICE": True,
    }
    monkeypatch.setattr(voice_service.emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(voice_service.emotion_service, "analyze_event", fake_analyze_event)
    monkeypatch.setattr(voice_service.emotion_service, "clear_voice_emotion_cache", lambda *args: None)
    monkeypatch.setattr(voice_service.config, "get", lambda key, default=None: settings.get(key, default))

    def analyze():
        return asyncio.run(voice_service._analyze_current_voice_emotion_pair(
            session_id="voice-session",
            media_path="/tmp/selected.webm",
            speech_text="我想點套餐",
            emotion_round_id="round-a",
            voice_turn_id="turn-1",
            voice_turn_index=1,
        ))

    reference = analyze()
    assert [(call["analysis_variant"], call["speech_text"]) for call in calls] == [
        ("media_only", ""),
    ]
    assert reference["analysis_variant"] == "media_only"

    calls.clear()
    settings["EMOTION_LLAMA_ANALYSIS_MODE"] = "media_plus_stt"
    reference = analyze()
    assert [(call["analysis_variant"], call["speech_text"]) for call in calls] == [
        ("media_plus_stt", "我想點套餐"),
    ]
    assert reference["analysis_variant"] == "media_plus_stt"


def test_stt_emotion_setting_is_public_and_defaults_on() -> None:
    import config

    assert config.DEFAULT_SETTINGS["EMOTION_LLAMA_INCLUDE_STT"] is True
    assert config.DEFAULT_SETTINGS["EMOTION_LLAMA_ANALYSIS_MODE"] == "media_plus_stt"
    assert "EMOTION_LLAMA_INCLUDE_STT" in config.PUBLIC_SETTINGS_KEYS
    assert "EMOTION_LLAMA_ANALYSIS_MODE" in config.PUBLIC_SETTINGS_KEYS


def test_admin_settings_show_default_emotion_prompt_when_saved_value_is_empty() -> None:
    import config

    effective = config.with_effective_emotion_prompt({"EMOTION_LLAMA_PROMPT": ""})
    assert effective["EMOTION_LLAMA_PROMPT"] == config.DEFAULT_SETTINGS["EMOTION_LLAMA_PROMPT"]

    custom = config.with_effective_emotion_prompt({"EMOTION_LLAMA_PROMPT": "自訂分析指令"})
    assert custom["EMOTION_LLAMA_PROMPT"] == "自訂分析指令"


def test_ordering_round_llm_uses_only_complete_five_field_evidence(monkeypatch) -> None:
    from services import emotion_service

    captured = {}
    complete = {
        "event_type": "voice_mode_ended", "emotion_round_id": "round-1", "status": "ok",
        "voice_turn_index": 1, "emotion": "anxious", "intensity": "medium",
        "facial": "眉頭微皺", "vocal": "語速偏快", "description": "顧客難以選擇套餐，需要簡短選項。",
    }
    incomplete = {**complete, "voice_turn_index": 2, "facial": ""}
    monkeypatch.setattr(emotion_service.emotion_log_repository, "get_logs", lambda limit: [complete, incomplete])

    def fake_generate(request):
        captured["request"] = request
        return SimpleNamespace(
            parsed={
                "current_situation": "顧客目前對套餐選擇感到焦慮。",
                "ordering_need": "需要少量且清楚的套餐選項。",
                "response_focus": "先確認偏好，再提供兩個選項。",
                "caution": "僅依一筆情緒證據判讀。",
            },
            safe_error="",
            model="qwen-test",
        )

    monkeypatch.setattr(emotion_service.llm_gateway_service, "generate", fake_generate)
    monkeypatch.setattr(emotion_service.config, "get", lambda key, default=None: default)
    result = asyncio.run(emotion_service.analyze_ordering_round("round-1"))

    assert result["status"] == "ok"
    assert result["evidence_count"] == 1
    assert result["decision_boundary"] == "admin_test_only"
    assert "眉頭微皺" in captured["request"].user_prompt
    assert '"facial":""' not in captured["request"].user_prompt


def test_successful_emotion_evidence_always_completes_all_five_fields(monkeypatch) -> None:
    from services import emotion_service

    def fake_collect(_request, **_kwargs):
        return MultimodalEvidence(
            provider="r1_omni", model_version="test", timestamp="2026-07-22T00:00:00+00:00",
            confidence=0.7, signals={"emotion": "anxious", "intensity": "medium"},
            quality="ok", latency_ms=1, has_evidence=True, status="ok",
        )

    monkeypatch.setattr(emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(emotion_service.multimodal_evidence_gateway, "collect_evidence", fake_collect)
    monkeypatch.setattr(emotion_service.emotion_log_repository, "append_log", lambda entry: entry)
    monkeypatch.setattr(
        emotion_service.llm_gateway_service,
        "generate",
        lambda request: SimpleNamespace(parsed=None, safe_error="repair unavailable"),
    )
    monkeypatch.setattr(emotion_service.config, "get", lambda key, default=None: {
        "EMOTION_LLAMA_QUALITY_CHECK": False,
        "EMOTION_PROVIDER": "r1_omni",
    }.get(key, default))

    entry = asyncio.run(emotion_service.analyze_event(
        "session-1", "/tmp/a.webm", "voice_mode_ended",
        speech_text="我不知道要選哪個套餐", emotion_round_id="round-1",
    ))

    assert entry["status"] == "ok"
    assert all(entry[field] for field in ("emotion", "intensity", "facial", "vocal", "description"))
    assert entry["facial"] == "未觀察到明確表情線索"
    assert entry["vocal"] == "未觀察到明確語調線索"


def test_voice_llm_influence_records_exact_snapshot_without_retaining_dialogue(monkeypatch) -> None:
    from services import emotion_service

    captured = []
    monkeypatch.setattr(emotion_service.emotion_log_repository, "append_log", captured.append)
    reference = {
        "provider": "r1_omni",
        "event_type": "voice_mode_started",
        "voice_turn_id": "turn-1",
        "voice_turn_index": 1,
        "observed_at_ms": 1234,
        "emotion": "anxious",
        "intensity": "high",
        "facial": "眉頭緊皺",
        "vocal": "語速偏快",
        "analysis_variant": "media_plus_stt",
        "comparison_pair_id": "pair-1",
    }

    entry = emotion_service.record_voice_llm_influence(
        session_id="voice-session",
        emotion_round_id="round-a",
        voice_turn_id="turn-2",
        voice_turn_index=2,
        user_speech="我的電話是 0912345678，請幫我點餐",
        ai_response="我理解您有些著急，先從餐點需求開始。",
        emotion_reference=reference,
        affect_voice_enabled=True,
    )

    assert captured == [entry]
    assert entry["event_type"] == "voice_llm_influence"
    assert entry["influence_status"] == "applied"
    assert entry["emotion_reference_used"] is True
    assert entry["referenced_voice_turn_id"] == "turn-1"
    assert entry["referenced_event_type"] == "voice_mode_started"
    assert entry["referenced_analysis_variant"] == "media_plus_stt"
    assert entry["referenced_comparison_pair_id"] == "pair-1"
    assert entry["emotion"] == "anxious"
    assert "user_speech_excerpt" not in entry
    assert "ai_response_excerpt" not in entry
    assert entry["user_speech_character_count"] == len("我的電話是 0912345678，請幫我點餐")
    assert entry["decision_boundary"] == "observation_only"


def test_voice_llm_influence_marks_parallel_analysis_not_ready(monkeypatch) -> None:
    from services import emotion_service

    monkeypatch.setattr(emotion_service.emotion_log_repository, "append_log", lambda entry: entry)
    entry = emotion_service.record_voice_llm_influence(
        session_id="voice-session",
        emotion_round_id="round-a",
        voice_turn_id="turn-1",
        voice_turn_index=1,
        user_speech="我要一份薯條",
        ai_response="好的。",
        emotion_reference=None,
        affect_voice_enabled=True,
    )

    assert entry["influence_status"] == "not_ready"
    assert entry["emotion_reference_used"] is False


def test_voice_influence_observability_failure_does_not_fail_reply(monkeypatch) -> None:
    from services import voice_service

    def fail_audit(**_kwargs):
        raise OSError("log unavailable")

    monkeypatch.setattr(voice_service.emotion_service, "record_voice_llm_influence", fail_audit)
    asyncio.run(voice_service._record_voice_emotion_influence(session_id="voice-session"))


def test_non_voice_event_cannot_update_voice_emotion_session() -> None:
    from services import emotion_service

    with pytest.raises(ValueError, match="voice emotion event type"):
        asyncio.run(emotion_service.analyze_event("s", "/tmp/a.webm", "payment_timeout"))
