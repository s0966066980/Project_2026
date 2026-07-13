"""Milestone 3B multimodal evidence gateway contracts."""

from __future__ import annotations

from models.multimodal_evidence import MultimodalEvidence, MultimodalEvidenceRequest


class FakeAdapter:
    def __init__(self, name: str, evidence: MultimodalEvidence | Exception):
        self.name = name
        self.calls = 0
        self._evidence = evidence

    def analyze(self, request: MultimodalEvidenceRequest) -> MultimodalEvidence:
        self.calls += 1
        if isinstance(self._evidence, Exception):
            raise self._evidence
        return self._evidence


def test_unavailable_provider_returns_no_evidence_without_raising() -> None:
    from services import multimodal_evidence_gateway, observability_service

    observability_service.reset_metrics_for_tests()
    adapter = FakeAdapter("emotion_llama", RuntimeError("connection refused"))
    evidence = multimodal_evidence_gateway.collect_evidence(
        MultimodalEvidenceRequest(
            media_path="/tmp/x.webm",
            question="q",
            timeout_seconds=1,
            provider_preference="emotion_llama",
        ),
        adapters={"emotion_llama": adapter, "null": multimodal_evidence_gateway.NullEvidenceAdapter()},
        enabled=True,
    )
    assert evidence.has_evidence is False
    assert evidence.safe_error
    assert "connection" in evidence.safe_error or "refused" in evidence.safe_error or evidence.quality in {
        "error",
        "unavailable",
        "timeout",
    }


def test_low_confidence_and_no_evidence_paths() -> None:
    from services import multimodal_evidence_gateway

    low = MultimodalEvidence(
        provider="emotion_llama",
        model_version="v1",
        timestamp="t",
        confidence=0.1,
        signals={"description": "blurry"},
        quality="low_confidence",
        latency_ms=12,
        has_evidence=True,
    )
    adapter = FakeAdapter("emotion_llama", low)
    evidence = multimodal_evidence_gateway.collect_evidence(
        MultimodalEvidenceRequest(media_path="m", question="q", provider_preference="emotion_llama"),
        adapters={"emotion_llama": adapter, "null": multimodal_evidence_gateway.NullEvidenceAdapter()},
        enabled=True,
    )
    assert evidence.has_evidence is True
    assert evidence.quality == "low_confidence"

    empty = MultimodalEvidence(
        provider="emotion_llama",
        model_version="v1",
        timestamp="t",
        confidence=None,
        signals={},
        quality="unavailable",
        latency_ms=1,
        has_evidence=False,
    )
    evidence2 = multimodal_evidence_gateway.collect_evidence(
        MultimodalEvidenceRequest(media_path="m", question="q", provider_preference="emotion_llama"),
        adapters={
            "emotion_llama": FakeAdapter("emotion_llama", empty),
            "null": multimodal_evidence_gateway.NullEvidenceAdapter(),
        },
        enabled=True,
    )
    assert evidence2.has_evidence is False


def test_disabled_gateway_uses_null_adapter() -> None:
    from services import multimodal_evidence_gateway

    evidence = multimodal_evidence_gateway.collect_evidence(
        MultimodalEvidenceRequest(media_path="m", question="q"),
        enabled=False,
    )
    assert evidence.provider == "null"
    assert evidence.has_evidence is False


def test_evidence_never_authorizes_transactions() -> None:
    from services import multimodal_evidence_gateway

    evidence = MultimodalEvidence(
        provider="emotion_llama",
        model_version="v1",
        timestamp="t",
        confidence=0.9,
        signals={"emotion": "frustrated"},
        quality="ok",
        latency_ms=5,
        has_evidence=True,
    )
    assert multimodal_evidence_gateway.evidence_is_not_transaction_authority(evidence)


def test_timeout_returns_degraded_evidence() -> None:
    from services import multimodal_evidence_gateway

    class Slow:
        name = "emotion_llama"

        def analyze(self, request):
            import time

            time.sleep(0.05)
            return MultimodalEvidence(
                provider="emotion_llama",
                model_version="v1",
                timestamp="t",
                confidence=0.9,
                signals={"emotion": "happy"},
                quality="ok",
                latency_ms=50,
                has_evidence=True,
            )

    evidence = multimodal_evidence_gateway.collect_evidence(
        MultimodalEvidenceRequest(
            media_path="m",
            question="q",
            timeout_seconds=0.01,
            provider_preference="emotion_llama",
        ),
        adapters={"emotion_llama": Slow(), "null": multimodal_evidence_gateway.NullEvidenceAdapter()},
        enabled=True,
    )
    assert evidence.has_evidence is False
    assert evidence.quality in {"timeout", "unavailable", "error"}
