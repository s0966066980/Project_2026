"""Milestone 5D: emotion production path uses Multimodal Evidence Gateway."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

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
        assert request.event_type == "voice_mode"
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
            event_type="voice_mode",
            speech_text="",
        )
    )
    assert entry["status"] in {"error", "no_evidence"}
    assert entry["decision_boundary"] == "evidence_only"
    assert entry.get("emotion", "") == ""


def test_analyze_event_maps_gateway_signals(monkeypatch) -> None:
    from services import emotion_service

    def fake_collect(request: MultimodalEvidenceRequest, **kwargs):
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
                "description": "customer appears frustrated",
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
        "EMOTION_LLAMA_AFFECT_BARRIER": False,
        "EMOTION_PROVIDER": "r1_omni",
        "EMOTION_LLAMA_TIMEOUT_SEC": 5,
    }.get(key, default))

    entry = asyncio.run(
        emotion_service.analyze_event("s2", "/tmp/a.webm", "payment_timeout", "hello")
    )
    assert entry["emotion"] == "frustrated"
    assert entry["provider"] == "r1_omni"
    assert entry["status"] == "ok"
    assert entry["decision_boundary"] == "evidence_only"
