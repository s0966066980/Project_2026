from models.multimodal_evidence import MultimodalEvidence, MultimodalEvidenceRequest
from services import multimodal_evidence_gateway as gateway


def request() -> MultimodalEvidenceRequest:
    return MultimodalEvidenceRequest(media_path="/tmp/clip.mp4", question="observe", timeout_seconds=0.2)


class EvidenceAdapter:
    name = "r1_omni"

    def __init__(self, result: MultimodalEvidence):
        self.result = result

    def analyze(self, _request):
        return self.result


def evidence(*, status="ok", has_evidence=True, quality="ok"):
    return MultimodalEvidence(
        provider="r1_omni",
        model_version="test-r1",
        timestamp="2026-01-01T00:00:00+00:00",
        confidence=0.9 if has_evidence else None,
        signals={"emotion": "happy"} if has_evidence else {},
        quality=quality,
        latency_ms=1,
        status=status,
        has_evidence=has_evidence,
    )


def test_default_runtime_exposes_only_r1_and_null_adapters():
    adapters = gateway.default_adapters()
    assert set(adapters) == {"r1_omni", "null"}
    assert gateway.evidence_is_not_transaction_authority(evidence())


def test_disabled_runtime_degrades_to_explicit_null_evidence():
    result = gateway.collect_evidence(request(), enabled=False)
    assert result.provider == "null"
    assert result.status == "disabled"
    assert result.has_evidence is False


def test_r1_evidence_is_returned_without_blocking_core_flow():
    result = gateway.collect_evidence(request(), adapters={"r1_omni": EvidenceAdapter(evidence())}, enabled=True)
    assert result.provider == "r1_omni"
    assert result.signals["emotion"] == "happy"


def test_unavailable_r1_runtime_returns_degraded_evidence():
    result = gateway.collect_evidence(
        request(),
        adapters={"r1_omni": EvidenceAdapter(evidence(status="error", has_evidence=False, quality="error"))},
        enabled=True,
    )
    assert result.has_evidence is False
    assert result.safe_metadata["degraded"] is True
