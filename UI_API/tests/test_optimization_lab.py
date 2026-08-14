import json
from datetime import datetime, timedelta, timezone

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from models.llm import LLMModelPolicy, LLMResponse
from modules.optimization_lab import OptimizationLabError
from modules.optimization_lab.module import AnalyzerRegistry, OptimizationLabModule
from modules.optimization_lab.sqlite_store import SQLiteOptimizationLabStore
from modules.voice_evidence.module import VoiceEvidenceModule
from modules.voice_evidence.sqlite_store import SQLiteVoiceEvidenceStore

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


class _AcceptingOfflineEvaluator:
    def evaluate(self, *, snapshot):
        return True


class _KnowledgePort:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.published = []

    def list_items(self, *, scope):
        return {"items": list(self.items)}

    def create_draft(self, **kwargs):
        return {"item_id": "knowledge-created", "row_revision": 1, **kwargs}

    def revise_draft(self, **kwargs):
        return {"item_id": kwargs["item_id"], "row_revision": kwargs["expected_row_revision"] + 1, **kwargs}

    def get_item(self, *, scope, item_id):
        return next(item for item in self.items if item["item_id"] == item_id)

    def request_publication(self, **kwargs):
        self.published.append(kwargs)
        return {"status": "indexing", "item_ids": kwargs["item_ids"]}


class _CapturingLocalAnalyzer:
    def __init__(self):
        self.snapshot = None

    def analyze(self, *, snapshot, profile):
        self.snapshot = snapshot
        hits = sum(1 for row in snapshot["evidence"] if row.get("rag_outcome") == "hit")
        misses = sum(1 for row in snapshot["evidence"] if row.get("rag_outcome") == "miss")
        return {
            "api_connectivity": {"status": "local", "evidence_count": len(snapshot["evidence"])},
            "commercial_outcomes": {"voice_evidence_count": len(snapshot["evidence"])},
            "voice_outcomes": {"completed": 1, "failed": 0, "retry_or_correction": 0},
            "rag_observations": {"hits": hits, "misses": misses},
        }


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


def test_customer_diagnostic_uses_shared_voice_evidence_and_sends_the_question_prompt(tmp_path):
    analyzer = _CapturingLocalAnalyzer()
    registry = AnalyzerRegistry(
        analyzers={"synthetic": object(), "ollama": analyzer},
        local_model="local-model",
        local_ready=True,
    )
    evidence = VoiceEvidenceModule(store=SQLiteVoiceEvidenceStore(tmp_path / "evidence.sqlite3"))
    evidence.project_terminal_turn(
        scope=LEGACY_DEFAULT_SCOPE,
        terminal={
            "voice_turn_id": "turn-shared-1",
            "observed_at": "2026-08-12T03:00:00+00:00",
            "status": "completed",
            "user_text": "診斷今日語音對話",
            "assistant_text": "已完成",
        },
    )
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        analyzers=registry,
        evidence_capability=evidence,
        clock=lambda: datetime(2026, 8, 12, 4, 0, tzinfo=timezone.utc),
    )
    question = module.create_diagnostic_question(
        scope=LEGACY_DEFAULT_SCOPE,
        display_name="今日語音診斷",
        prompt="診斷今日語音對話",
    )

    report = module.simulate(
        scope=LEGACY_DEFAULT_SCOPE,
        store_date="2026-08-12",
        timezone_name="Asia/Taipei",
        profile_id="ollama",
        model="local-model",
        effort="standard",
        data_scope="customer_evidence",
        question_id=question["question_id"],
    )

    assert report["evidence_count"] == 1
    assert report["evidence_ids"][0].startswith("vie_")
    assert analyzer.snapshot["diagnostic_question"]["prompt"] == "診斷今日語音對話"
    assert analyzer.snapshot["evidence"][0]["voice_outcome"] == "success"
    assert "user_text" not in analyzer.snapshot["evidence"][0]


def test_rag_not_run_is_not_counted_as_a_knowledge_gap(tmp_path):
    analyzer = _CapturingLocalAnalyzer()
    evidence = VoiceEvidenceModule(store=SQLiteVoiceEvidenceStore(tmp_path / "evidence.sqlite3"))
    for index in range(3):
        evidence.project_terminal_turn(
            scope=LEGACY_DEFAULT_SCOPE,
            terminal={
                "voice_turn_id": f"turn-not-run-{index}",
                "observed_at": f"2026-08-12T03:0{index}:00+00:00",
                "status": "completed",
                "rag_outcome": "not_run",
            },
        )
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        analyzers=AnalyzerRegistry(
            analyzers={"synthetic": object(), "ollama": analyzer},
            local_model="local-model",
            local_ready=True,
        ),
        evidence_capability=evidence,
        offline_evaluator=_AcceptingOfflineEvaluator(),
        clock=lambda: datetime(2026, 8, 12, 4, 0, tzinfo=timezone.utc),
    )
    question = module.create_diagnostic_question(
        scope=LEGACY_DEFAULT_SCOPE,
        display_name="今日語音診斷",
        prompt="診斷今日語音對話",
    )

    report = module.simulate(
        scope=LEGACY_DEFAULT_SCOPE,
        store_date="2026-08-12",
        timezone_name="Asia/Taipei",
        profile_id="ollama",
        model="local-model",
        effort="standard",
        data_scope="customer_evidence",
        question_id=question["question_id"],
    )

    rag = next(section["data"] for section in report["sections"] if section["id"] == "rag_observations")
    assert rag["misses"] == 0
    assert "knowledge_change_candidate" not in report


def test_shared_voice_rag_miss_can_create_a_reviewable_candidate(tmp_path):
    analyzer = _CapturingLocalAnalyzer()
    evidence = VoiceEvidenceModule(store=SQLiteVoiceEvidenceStore(tmp_path / "evidence.sqlite3"))
    for index in range(3):
        evidence.project_terminal_turn(
            scope=LEGACY_DEFAULT_SCOPE,
            terminal={
                "voice_turn_id": f"turn-miss-{index}",
                "observed_at": f"2026-08-12T03:0{index}:00+00:00",
                "status": "completed",
                "rag_outcome": "miss",
            },
        )
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        analyzers=AnalyzerRegistry(
            analyzers={"synthetic": object(), "ollama": analyzer},
            local_model="local-model",
            local_ready=True,
        ),
        evidence_capability=evidence,
        offline_evaluator=_AcceptingOfflineEvaluator(),
        clock=lambda: datetime(2026, 8, 12, 4, 0, tzinfo=timezone.utc),
    )
    question = module.create_diagnostic_question(
        scope=LEGACY_DEFAULT_SCOPE,
        display_name="今日語音診斷",
        prompt="診斷今日語音對話",
    )

    report = module.simulate(
        scope=LEGACY_DEFAULT_SCOPE,
        store_date="2026-08-12",
        timezone_name="Asia/Taipei",
        profile_id="ollama",
        model="local-model",
        effort="standard",
        data_scope="customer_evidence",
        question_id=question["question_id"],
    )

    assert report["knowledge_change_candidate"]["action"] == "create"
    assert report["dialogue"]["answer"].endswith("需要我幫你將分析結果加入 RAG 嗎？")


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
    assert report["diagnostic_question"]["prompt"] == "診斷今日語音對話"
    assert "alice@example.com" not in json.dumps(report, ensure_ascii=False)


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
    question = module.create_diagnostic_question(
        scope=LEGACY_DEFAULT_SCOPE,
        display_name="今日語音診斷",
        prompt="診斷今日語音對話",
    )

    report = module.simulate(
        scope=LEGACY_DEFAULT_SCOPE,
        store_date="2026-08-12",
        timezone_name="Asia/Taipei",
        profile_id="ollama",
        model="qwen3.5:4b",
        effort="standard",
        question_id=question["question_id"],
    )

    assert len(calls) == 1
    assert calls[0].model_policy is LLMModelPolicy.LOCAL_ONLY
    assert calls[0].model_name == "qwen3.5:4b"
    assert "診斷今日語音對話" in calls[0].user_prompt
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


def test_each_store_gets_one_editable_default_diagnostic_question(tmp_path):
    module = _module(tmp_path)

    questions = module.list_diagnostic_questions(scope=LEGACY_DEFAULT_SCOPE)

    assert len(questions) == 1
    assert questions[0]["display_name"] == "今日語音診斷"
    assert questions[0]["prompt"] == "診斷今日語音對話"

    module.update_diagnostic_question(
        scope=LEGACY_DEFAULT_SCOPE,
        question_id=questions[0]["question_id"],
        display_name="今日語音回顧",
        prompt="診斷今日語音對話並整理 RAG 缺口",
    )
    updated = module.list_diagnostic_questions(scope=LEGACY_DEFAULT_SCOPE)
    assert updated[0]["display_name"] == "今日語音回顧"
    assert updated[0]["prompt"].endswith("RAG 缺口")


def test_diagnostic_question_can_be_created_and_permanently_deleted(tmp_path):
    module = _module(tmp_path)

    created = module.create_diagnostic_question(
        scope=LEGACY_DEFAULT_SCOPE,
        display_name="RAG 缺口檢查",
        prompt="找出今日未命中的常見問題",
    )
    assert created["display_name"] == "RAG 缺口檢查"
    questions = module.list_diagnostic_questions(scope=LEGACY_DEFAULT_SCOPE)
    assert len(questions) == 2
    assert created["question_id"] in {row["question_id"] for row in questions}

    module.delete_diagnostic_question(scope=LEGACY_DEFAULT_SCOPE, question_id=created["question_id"])
    assert all(
        row["question_id"] != created["question_id"]
        for row in module.list_diagnostic_questions(scope=LEGACY_DEFAULT_SCOPE)
    )


def test_deleting_default_question_does_not_recreate_it(tmp_path):
    module = _module(tmp_path)
    question = module.list_diagnostic_questions(scope=LEGACY_DEFAULT_SCOPE)[0]

    module.delete_diagnostic_question(scope=LEGACY_DEFAULT_SCOPE, question_id=question["question_id"])

    assert module.list_diagnostic_questions(scope=LEGACY_DEFAULT_SCOPE) == []


def test_diagnostic_question_requires_both_display_name_and_prompt(tmp_path):
    module = _module(tmp_path)

    with pytest.raises(OptimizationLabError, match="diagnostic_question_fields_required"):
        module.create_diagnostic_question(scope=LEGACY_DEFAULT_SCOPE, display_name="", prompt="診斷")
    with pytest.raises(OptimizationLabError, match="diagnostic_question_fields_required"):
        module.create_diagnostic_question(scope=LEGACY_DEFAULT_SCOPE, display_name="診斷", prompt="")


def test_diagnostic_run_freezes_question_and_returns_latest_dialogue_result(tmp_path):
    module = _module(tmp_path)
    question = module.create_diagnostic_question(
        scope=LEGACY_DEFAULT_SCOPE,
        display_name="今日 RAG 檢查",
        prompt="診斷今日語音對話並找出 RAG 缺口",
    )
    evidence = _fixture(module)

    report = module.simulate(
        scope=LEGACY_DEFAULT_SCOPE,
        store_date="2026-08-12",
        timezone_name="Asia/Taipei",
        profile_id="synthetic",
        model="synthetic-rule-v1",
        effort="standard",
        question_id=question["question_id"],
    )

    assert report["diagnostic_question"] == {
        "question_id": question["question_id"],
        "display_name": "今日 RAG 檢查",
        "prompt": "診斷今日語音對話並找出 RAG 缺口",
    }
    assert report["dialogue"]["question"] == "診斷今日語音對話並找出 RAG 缺口"
    assert report["dialogue"]["answer"]
    assert module.latest_report(scope=LEGACY_DEFAULT_SCOPE)["report_id"] == report["report_id"]

    module.delete_diagnostic_question(scope=LEGACY_DEFAULT_SCOPE, question_id=question["question_id"])
    retained = module.get_report(scope=LEGACY_DEFAULT_SCOPE, report_id=report["report_id"])
    assert retained["diagnostic_question"]["display_name"] == "今日 RAG 檢查"
    assert retained["evidence_ids"] == [evidence["evidence_id"]]


def test_diagnostic_run_rejects_an_unknown_question(tmp_path):
    module = _module(tmp_path)

    with pytest.raises(OptimizationLabError, match="diagnostic_question_not_found"):
        module.simulate(
            scope=LEGACY_DEFAULT_SCOPE,
            store_date="2026-08-12",
            timezone_name="Asia/Taipei",
            profile_id="synthetic",
            model="synthetic-rule-v1",
            effort="standard",
            question_id="missing-question",
        )


def test_repeated_rag_gap_creates_one_reviewable_knowledge_candidate(tmp_path):
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        offline_evaluator=_AcceptingOfflineEvaluator(),
        knowledge=_KnowledgePort(),
    )
    for index in range(3):
        _fixture(module, failure_type="rag_miss", observed_at=f"2026-08-12T03:0{index}:00+00:00")

    report = _simulate(module)

    candidate = report["knowledge_change_candidate"]
    assert candidate["status"] == "pending"
    assert candidate["action"] == "create"
    assert candidate["proposed"]["content"]
    assert report["dialogue"]["answer"].endswith("需要我幫你將分析結果加入 RAG 嗎？")


def test_new_diagnosis_requires_explicit_abandonment_of_pending_candidate(tmp_path):
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        offline_evaluator=_AcceptingOfflineEvaluator(),
        knowledge=_KnowledgePort(),
    )
    for index in range(3):
        _fixture(module, failure_type="rag_miss", observed_at=f"2026-08-12T03:0{index}:00+00:00")
    _simulate(module)

    with pytest.raises(OptimizationLabError, match="pending_candidate_requires_abandonment"):
        _simulate(module)

    candidate = module.pending_candidate(scope=LEGACY_DEFAULT_SCOPE)
    assert candidate["status"] == "pending"
    abandoned = module.abandon_candidate(scope=LEGACY_DEFAULT_SCOPE, candidate_id=candidate["candidate_id"])
    assert abandoned["status"] == "abandoned"
    assert module.pending_candidate(scope=LEGACY_DEFAULT_SCOPE) is None


def test_candidate_edit_is_revalidated_and_confirmation_publishes_new_knowledge(tmp_path):
    knowledge = _KnowledgePort()
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        offline_evaluator=_AcceptingOfflineEvaluator(),
        knowledge=knowledge,
    )
    for index in range(3):
        _fixture(module, failure_type="rag_miss", observed_at=f"2026-08-12T03:0{index}:00+00:00")
    _simulate(module)
    candidate = module.pending_candidate(scope=LEGACY_DEFAULT_SCOPE)

    edited = module.edit_candidate(
        scope=LEGACY_DEFAULT_SCOPE,
        candidate_id=candidate["candidate_id"],
        title="今日語音 RAG 知識",
        category="other",
        content_type="question_answer",
        content="問題：語音對話分析\n\n答案：請依正式門市政策回答。",
    )
    assert edited["offline_acceptance"] == "passed"
    confirmed = module.confirm_candidate(
        scope=LEGACY_DEFAULT_SCOPE,
        candidate_id=candidate["candidate_id"],
        actor="admin-1",
    )
    assert confirmed["status"] == "confirmed"
    assert knowledge.published[0]["item_ids"] == ["knowledge-created"]


def test_candidate_update_refuses_a_changed_target_knowledge_item(tmp_path):
    knowledge = _KnowledgePort(
        items=[
            {
                "item_id": "knowledge-1",
                "row_revision": 4,
                "title": "RAG",
                "category": "other",
                "content_type": "question_answer",
                "content": "rag_miss",
            }
        ]
    )
    module = OptimizationLabModule(
        store=SQLiteOptimizationLabStore(tmp_path / "optimization.sqlite3"),
        offline_evaluator=_AcceptingOfflineEvaluator(),
        knowledge=knowledge,
    )
    for index in range(3):
        _fixture(module, failure_type="rag_miss", observed_at=f"2026-08-12T03:0{index}:00+00:00")
    _simulate(module)
    candidate = module.pending_candidate(scope=LEGACY_DEFAULT_SCOPE)
    assert candidate["action"] == "update"
    knowledge.items[0]["row_revision"] = 5

    with pytest.raises(OptimizationLabError, match="knowledge_candidate_stale"):
        module.confirm_candidate(
            scope=LEGACY_DEFAULT_SCOPE,
            candidate_id=candidate["candidate_id"],
            actor="admin-1",
        )
