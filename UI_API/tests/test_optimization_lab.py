import json
from datetime import datetime, timedelta, timezone

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from models.llm import LLMModelPolicy, LLMResponse
from modules.optimization_lab import OptimizationLabError
from modules.optimization_lab.module import AnalyzerRegistry, OptimizationLabModule
from modules.optimization_lab.sqlite_store import SQLiteOptimizationLabStore

pytestmark = [pytest.mark.unit]


def _clock_box():
    return [datetime(2026, 8, 12, 4, 0, tzinfo=timezone.utc)]


def _module(tmp_path, clock_box=None, *, offline=None):
    clock_box = clock_box or _clock_box()
    return OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        clock=lambda: clock_box[0],
        offline_evaluator=offline,
    )


def _fixture(module, *, failure_type="", observed_at="2026-08-12T03:00:00+00:00"):
    return module.ingest_evidence(
        scope=LEGACY_DEFAULT_SCOPE,
        synthetic=True,
        payload={
            "observed_at": observed_at,
            "transcript": "請找 alice@example.com 的餐點，卡號 4111111111111111",
            "assistant_text": "好的，電話 0912-345-678 的訂單已建立",
            "rag_hit": {"hit": not bool(failure_type), "count": 1 if not failure_type else 0},
            "voice_outcome": "failed" if failure_type else "success",
            "failure_type": failure_type,
            "retry_outcome": "none",
        },
    )


def _simulate(module):
    return module.simulate(
        scope=LEGACY_DEFAULT_SCOPE,
        store_date="2026-08-12",
        timezone_name="Asia/Taipei",
        profile_id="synthetic",
        model="synthetic-rule-v1",
        effort="standard",
    )


def test_evidence_is_masked_and_rejects_identity_or_media_fields(tmp_path):
    module = _module(tmp_path)
    record = _fixture(module)

    assert "alice@example.com" not in record["transcript_masked"]
    assert "0912-345-678" not in record["assistant_text_masked"]
    assert "4111111111111111" not in record["transcript_masked"]

    for forbidden_field, value in (
        ("audio_ref", "/tmp/raw.webm"),
        ("member", "member-1"),
        ("session", "session-1"),
        ("order", "order-1"),
        ("payment", "payment-1"),
    ):
        with pytest.raises(OptimizationLabError, match="raw_or_identity_field_not_allowed"):
            module.ingest_evidence(
                scope=LEGACY_DEFAULT_SCOPE,
                synthetic=True,
                payload={forbidden_field: value, "transcript": "raw"},
            )


def test_snapshot_is_store_scoped_and_freezes_evidence(tmp_path):
    module = _module(tmp_path)
    first = _fixture(module)
    report = _simulate(module)
    _fixture(module, observed_at="2026-08-12T03:30:00+00:00")

    assert report["evidence_ids"] == [first["evidence_id"]]
    assert report["partial"] is True
    assert len(report["sections"]) == 6


def test_two_occurrences_are_observation_and_three_are_unverified_reference_guidance(tmp_path):
    module = _module(tmp_path)
    _fixture(module, failure_type="stt_timeout")
    _fixture(module, failure_type="stt_timeout", observed_at="2026-08-12T03:01:00+00:00")
    observation = _simulate(module)
    findings = observation["sections"][-1]["data"]["findings"]
    assert findings[0]["evidence_level"] == "Observation Signal"

    _fixture(module, failure_type="stt_timeout", observed_at="2026-08-12T03:02:00+00:00")
    report = _simulate(module)
    finding = report["sections"][-1]["data"]["findings"][0]
    assert finding["evidence_level"] == "Reference Guidance"
    assert finding["offline_acceptance"] == "unverified"
    assert "prompt" not in json.dumps(report, ensure_ascii=False).lower()


def test_report_never_copies_conversation_and_expansion_requires_step_up(tmp_path):
    module = _module(tmp_path)
    evidence = _fixture(module)
    report = _simulate(module)
    encoded = json.dumps(report, ensure_ascii=False)
    assert "alice@example.com" not in encoded
    assert "訂單已建立" not in encoded

    with pytest.raises(OptimizationLabError, match="step_up_required"):
        module.expand_evidence(
            scope=LEGACY_DEFAULT_SCOPE,
            report_id=report["report_id"],
            evidence_id=evidence["evidence_id"],
            actor="admin",
            step_up_valid_until=None,
        )
    expanded = module.expand_evidence(
        scope=LEGACY_DEFAULT_SCOPE,
        report_id=report["report_id"],
        evidence_id=evidence["evidence_id"],
        actor="admin",
        step_up_valid_until=datetime(2026, 8, 12, 5, 0, tzinfo=timezone.utc),
    )
    assert expanded["evidence_id"] == evidence["evidence_id"]


def test_provider_customer_scope_fails_closed_before_egress(tmp_path):
    module = _module(tmp_path)
    with pytest.raises(OptimizationLabError, match="analyzer_data_scope_not_supported"):
        module.simulate(
            scope=LEGACY_DEFAULT_SCOPE,
            store_date="2026-08-11",
            timezone_name="Asia/Taipei",
            profile_id="synthetic",
            model="synthetic-rule-v1",
            effort="standard",
            data_scope="customer_evidence",
        )


def test_local_ollama_analyzer_is_local_only_and_report_is_bounded(tmp_path, monkeypatch):
    calls = []

    def fake_generate(request):
        calls.append(request)
        return LLMResponse(
            content='{"api_connectivity":{"status":"local"}}',
            provider="ollama",
            model="qwen3.5:4b",
            latency_ms=12.0,
            usage=None,
            finish_reason="stop",
            safe_error="",
            parsed={
                "api_connectivity": {
                    "status": "local",
                    "evidence_count": 1,
                    "transcript": "must not persist",
                },
                "commercial_outcomes": {"voice_evidence_count": 1},
                "voice_outcomes": {"completed": 1, "failed": 0, "retry_or_correction": 0},
                "rag_observations": {"hits": 1, "misses": 0},
            },
            prompt_version="optimization-lab-ollama-v1",
        )

    monkeypatch.setattr("services.llm_gateway_service.generate", fake_generate)
    registry = AnalyzerRegistry(local_model="qwen3.5:4b", local_ready=True)
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        analyzers=registry,
    )
    _fixture(module)

    report = module.simulate(
        scope=LEGACY_DEFAULT_SCOPE,
        store_date="2026-08-12",
        timezone_name="Asia/Taipei",
        profile_id="ollama",
        model="qwen3.5:4b",
        effort="standard",
    )

    assert len(calls) == 1
    assert calls[0].model_policy is LLMModelPolicy.LOCAL_ONLY
    assert calls[0].model_name == "qwen3.5:4b"
    assert report["analyzer"]["provider"] == "Ollama"
    assert "must not persist" not in json.dumps(report, ensure_ascii=False)


def test_local_ollama_failure_does_not_fallback_to_synthetic(tmp_path, monkeypatch):
    def fake_generate(_request):
        return LLMResponse(
            content="",
            provider="ollama",
            model="qwen3.5:4b",
            latency_ms=1.0,
            usage=None,
            finish_reason="error",
            safe_error="provider_timeout",
            parsed=None,
            prompt_version="optimization-lab-ollama-v1",
        )

    monkeypatch.setattr("services.llm_gateway_service.generate", fake_generate)
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        analyzers=AnalyzerRegistry(local_model="qwen3.5:4b", local_ready=True),
    )
    _fixture(module)

    with pytest.raises(OptimizationLabError, match="local_ollama_analysis_failed"):
        module.simulate(
            scope=LEGACY_DEFAULT_SCOPE,
            store_date="2026-08-12",
            timezone_name="Asia/Taipei",
            profile_id="ollama",
            model="qwen3.5:4b",
            effort="standard",
        )


def test_local_ollama_schema_echo_is_rejected_without_fallback(tmp_path, monkeypatch):
    def fake_generate(_request):
        return LLMResponse(
            content='{"evidence": ["echo"], "partial": true}',
            provider="ollama",
            model="qwen3.5:4b",
            latency_ms=1.0,
            usage=None,
            finish_reason="stop",
            safe_error="",
            parsed={"evidence": ["echo"], "partial": True},
            prompt_version="optimization-lab-ollama-v1",
        )

    monkeypatch.setattr("services.llm_gateway_service.generate", fake_generate)
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        analyzers=AnalyzerRegistry(local_model="qwen3.5:4b", local_ready=True),
    )
    _fixture(module)

    with pytest.raises(OptimizationLabError, match="local_ollama_analysis_failed"):
        module.simulate(
            scope=LEGACY_DEFAULT_SCOPE,
            store_date="2026-08-12",
            timezone_name="Asia/Taipei",
            profile_id="ollama",
            model="qwen3.5:4b",
            effort="standard",
        )


def test_expired_evidence_and_reports_are_deleted(tmp_path):
    clock_box = _clock_box()
    module = _module(tmp_path, clock_box)
    evidence = _fixture(module)
    report = _simulate(module)
    clock_box[0] += timedelta(days=31)

    assert module.cleanup_expired() >= 2
    with pytest.raises(OptimizationLabError, match="report_not_found"):
        module.get_report(scope=LEGACY_DEFAULT_SCOPE, report_id=report["report_id"])
    assert module._store.get_evidence(scope=LEGACY_DEFAULT_SCOPE, evidence_id=evidence["evidence_id"]) is None
