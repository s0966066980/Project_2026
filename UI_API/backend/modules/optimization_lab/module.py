"""P4 Daily Optimization Simulation domain and safety boundary.

This module accepts explicitly selected, de-identified evidence and emits one
bounded six-section report. It has no settings, RAG, campaign, recommendation,
filesystem, shell, or production-write port. Provider execution is an injected
port; the registry exposes deterministic synthetic fixtures and a local Ollama
analyzer. Missing local readiness or malformed model output fails closed rather
than silently falling back.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from models.commercial_scope import CommercialScope

from .contracts import (
    ANALYZER_DATA_SCOPES,
    AnalyzerProfile,
    OptimizationLabError,
)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
_LONG_NUMBER = re.compile(r"(?<!\w)\d{10,}(?!\w)")
_MAX_TEXT = 12_000
_FORBIDDEN_KEYS = frozenset(
    {
        "audio",
        "audio_base64",
        "audio_ref",
        "camera",
        "device_id",
        "emotion",
        "member_id",
        "member_ref",
        "media",
        "order_id",
        "order_ref",
        "payment_id",
        "payment_ref",
        "session_id",
        "video",
        "video_ref",
        "member",
        "device",
        "session",
        "order",
        "payment",
    }
)
_SAFE_FAILURES = frozenset(
    {
        "",
        "none",
        "stt_timeout",
        "llm_timeout",
        "tts_timeout",
        "transport_failure",
        "workflow_failure",
        "rag_miss",
        "unknown",
    }
)
_SAFE_VOICE_OUTCOMES = frozenset({"success", "failed", "unknown", "not_observed"})
_SAFE_RETRY_OUTCOMES = frozenset({"", "none", "retried", "corrected", "abandoned"})
_ANALYZER_SECTION_KEYS = frozenset(
    {
        "api_connectivity",
        "commercial_outcomes",
        "voice_outcomes",
        "rag_observations",
    }
)
_DEFAULT_DIAGNOSTIC_QUESTION_NAME = "今日語音診斷"
_DEFAULT_DIAGNOSTIC_QUESTION_PROMPT = "診斷今日語音對話"
_DIAGNOSTIC_QUESTION_NAME_LIMIT = 120
_DIAGNOSTIC_QUESTION_PROMPT_LIMIT = 4_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: object, *, code: str = "invalid_timestamp") -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return _now()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OptimizationLabError(code) from exc
    if parsed.tzinfo is None:
        raise OptimizationLabError(code)
    return parsed.astimezone(timezone.utc)


def _text(value: object, *, limit: int = _MAX_TEXT) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise OptimizationLabError("text_too_large")
    return text


def _redact(text: str) -> str:
    """Mask known direct identifiers before evidence reaches persistence."""

    masked = _EMAIL.sub("<redacted-email>", text)
    masked = _PHONE.sub("<redacted-phone>", masked)
    return _LONG_NUMBER.sub("<redacted-number>", masked)


def _safe_rag_hit(value: object) -> dict[str, Any]:
    if value is None:
        return {"hit": False, "count": 0}
    if not isinstance(value, dict):
        raise OptimizationLabError("invalid_rag_outcome")
    allowed = {"hit", "count", "source_count", "status"}
    if set(value) - allowed:
        raise OptimizationLabError("rag_content_not_allowed")
    status = str(value.get("status") or "observed").strip()[:40]
    if status not in {"observed", "unavailable", "error"}:
        raise OptimizationLabError("invalid_rag_outcome")
    try:
        count = max(0, min(int(value.get("count", 0) or 0), 1000))
        source_count = max(0, min(int(value.get("source_count", 0) or 0), 1000))
    except (TypeError, ValueError) as exc:
        raise OptimizationLabError("invalid_rag_outcome") from exc
    return {"hit": bool(value.get("hit", False)), "count": count, "source_count": source_count, "status": status}


def _bounded_metrics(
    value: object, *, numeric_keys: tuple[str, ...], text_keys: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Keep provider output from smuggling conversation content into a report."""

    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key in numeric_keys:
        if key not in value:
            continue
        try:
            result[key] = max(0, min(int(value[key] or 0), 1_000_000))
        except (TypeError, ValueError):
            continue
    for key in text_keys:
        if key in value:
            result[key] = _text(value[key], limit=80)
    return result


def _normalize_analyzer_result(value: object) -> dict[str, Any]:
    """Validate the provider envelope before it can influence a report.

    Local models are still untrusted output.  The report only accepts the
    four documented metric objects; an echo, free-form explanation, or an
    empty object is a hard failure instead of an implicit synthetic fallback.
    Inner fields are bounded by ``_bounded_metrics`` when the report is built.
    """

    if not isinstance(value, dict):
        raise OptimizationLabError("local_ollama_schema_invalid")
    unknown = sorted(str(key) for key in value if str(key) not in _ANALYZER_SECTION_KEYS)
    if unknown:
        raise OptimizationLabError(
            "local_ollama_schema_invalid",
            details={"unknown_fields": unknown[:8]},
        )
    known = {key: section for key, section in value.items() if key in _ANALYZER_SECTION_KEYS}
    if not known or any(not isinstance(section, dict) for section in known.values()):
        raise OptimizationLabError("local_ollama_schema_invalid")
    return known


def _scope_ids(scope: CommercialScope) -> tuple[str, str]:
    return str(scope.tenant_id), str(scope.store_id)


def _diagnostic_question_fields(display_name: object, prompt: object) -> tuple[str, str]:
    name = _text(display_name, limit=_DIAGNOSTIC_QUESTION_NAME_LIMIT)
    instruction = _text(prompt, limit=_DIAGNOSTIC_QUESTION_PROMPT_LIMIT)
    if not name or not instruction:
        raise OptimizationLabError("diagnostic_question_fields_required")
    return name, instruction


class OptimizationStore(Protocol):
    def ensure_default_diagnostic_question(self, *, scope: CommercialScope, record: dict[str, Any]) -> None: ...

    def list_diagnostic_questions(self, *, scope: CommercialScope) -> list[dict[str, Any]]: ...

    def create_diagnostic_question(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]: ...

    def get_diagnostic_question(self, *, scope: CommercialScope, question_id: str) -> dict[str, Any] | None: ...

    def update_diagnostic_question(
        self, *, scope: CommercialScope, question_id: str, record: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def delete_diagnostic_question(self, *, scope: CommercialScope, question_id: str) -> bool: ...

    def create_candidate(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]: ...

    def get_pending_candidate(self, *, scope: CommercialScope) -> dict[str, Any] | None: ...

    def get_candidate(self, *, scope: CommercialScope, candidate_id: str) -> dict[str, Any] | None: ...

    def update_candidate(
        self, *, scope: CommercialScope, candidate_id: str, record: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def create_evidence(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]: ...

    def list_evidence(
        self,
        *,
        scope: CommercialScope,
        start_at: str,
        end_at: str,
        cutoff_at: str,
        synthetic_only: bool,
    ) -> list[dict[str, Any]]: ...

    def get_evidence(self, *, scope: CommercialScope, evidence_id: str) -> dict[str, Any] | None: ...

    def create_snapshot(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]: ...

    def save_report(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]: ...

    def update_report(self, *, scope: CommercialScope, report_id: str, record: dict[str, Any]) -> dict[str, Any]: ...

    def get_report(self, *, scope: CommercialScope, report_id: str) -> dict[str, Any] | None: ...

    def latest_report(self, *, scope: CommercialScope) -> dict[str, Any] | None: ...

    def record_egress_audit(self, *, scope: CommercialScope, record: dict[str, Any]) -> None: ...

    def record_access_audit(self, *, scope: CommercialScope, record: dict[str, Any]) -> None: ...

    def cleanup_expired(self, *, now: str) -> int: ...


class Analyzer(Protocol):
    def analyze(self, *, snapshot: dict[str, Any], profile: AnalyzerProfile) -> dict[str, Any]: ...


class OfflineEvaluator(Protocol):
    def evaluate(self, *, snapshot: dict[str, Any]) -> bool: ...


class ProviderAuthorization(Protocol):
    def authorize(
        self,
        *,
        scope: CommercialScope,
        profile: AnalyzerProfile,
        model: str,
        effort: str,
    ) -> str: ...


class KnowledgePort(Protocol):
    def list_items(self, *, scope: CommercialScope) -> dict[str, Any]: ...

    def get_item(self, *, scope: CommercialScope, item_id: str) -> dict[str, Any]: ...

    def create_draft(self, **kwargs: Any) -> dict[str, Any]: ...

    def revise_draft(self, **kwargs: Any) -> dict[str, Any]: ...

    def request_publication(self, **kwargs: Any) -> dict[str, Any]: ...


class VoiceEvidenceCapability(Protocol):
    def snapshot(
        self,
        *,
        scope: CommercialScope,
        observed_from: str,
        observed_to: str,
        cutoff_at: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def reconciliation(self, *, scope: CommercialScope, observed_from: str, observed_to: str) -> dict[str, Any]: ...


class DenyProviderAuthorization:
    def authorize(self, **_: Any) -> str:
        raise OptimizationLabError("customer_evidence_authorization_required")


class NeverAcceptedOfflineEvaluator:
    def evaluate(self, **_: Any) -> bool:
        return False


class SyntheticAnalyzer:
    """A deterministic analyzer used only for synthetic fixtures."""

    def analyze(self, *, snapshot: dict[str, Any], profile: AnalyzerProfile) -> dict[str, Any]:
        evidence = list(snapshot.get("evidence") or [])
        failures = [row for row in evidence if row.get("voice_outcome") == "failed"]
        rag_hits = sum(1 for row in evidence if _effective_rag_outcome(row) == "hit")
        rag_misses = sum(1 for row in evidence if _effective_rag_outcome(row) == "miss")
        return {
            "provider_observations": {
                "analyzer": profile.profile_id,
                "version": profile.version,
                "model": "synthetic-rule-v1",
                "effort": "standard",
            },
            "api_connectivity": {"status": "synthetic", "evidence_count": len(evidence)},
            "commercial_outcomes": {"voice_evidence_count": len(evidence)},
            "voice_outcomes": {
                "completed": len(evidence) - len(failures),
                "failed": len(failures),
                "retry_or_correction": sum(1 for row in evidence if row.get("retry_outcome") not in {"", "none"}),
            },
            "rag_observations": {"hits": rag_hits, "misses": rag_misses},
        }


class OllamaAnalyzer:
    """Run the bounded Optimization Lab analysis through the local Ollama gateway.

    The gateway is explicitly called with ``LOCAL_ONLY``. A timeout, malformed
    response, or unavailable model is surfaced to the caller; it never falls
    back to the synthetic analyzer or to a cloud provider.
    """

    def __init__(self, *, timeout_seconds: float = 45.0):
        self._timeout_seconds = max(1.0, float(timeout_seconds))

    def analyze(self, *, snapshot: dict[str, Any], profile: AnalyzerProfile) -> dict[str, Any]:
        from models.llm import LLMModelPolicy, LLMRequest
        from services import llm_gateway_service

        model = profile.models[0] if profile.models else ""
        if not model:
            raise OptimizationLabError("local_ollama_model_not_configured")
        evidence = []
        for row in list(snapshot.get("evidence") or [])[:200]:
            evidence.append(
                {
                    "evidence_id": str(row.get("evidence_id") or ""),
                    "observed_at": str(row.get("observed_at") or ""),
                    "transcript_masked": str(row.get("transcript_masked") or "")[:500],
                    "assistant_text_masked": str(row.get("assistant_text_masked") or "")[:500],
                    "rag_hit": row.get("rag_hit") or {},
                    "voice_outcome": str(row.get("voice_outcome") or "unknown"),
                    "failure_type": str(row.get("failure_type") or ""),
                    "retry_outcome": str(row.get("retry_outcome") or "none"),
                }
            )
        request = LLMRequest(
            task="optimization_lab",
            system_prompt=(
                "You are the local-only Optimization Lab analyzer. Analyze only the supplied "
                "de-identified evidence. Return one JSON object with exactly these optional "
                "objects: api_connectivity {status,evidence_count}, commercial_outcomes "
                "{voice_evidence_count}, voice_outcomes {completed,failed,retry_or_correction}, "
                "rag_observations {hits,misses}. Use bounded numeric counts and short status "
                "values. Follow the supplied diagnostic_question_prompt as the analysis instruction, "
                "but never expand evidence scope, override offline safety, or publish changes. "
                "Never return transcript, assistant text, identifiers, recommendations, settings, "
                "or production mutations."
            ),
            user_prompt=json.dumps(
                {
                    "store_date": snapshot.get("store_date"),
                    "timezone": snapshot.get("timezone"),
                    "partial": bool(snapshot.get("partial")),
                    "diagnostic_question_prompt": str((snapshot.get("diagnostic_question") or {}).get("prompt") or "")[
                        :4000
                    ],
                    "evidence": evidence,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            timeout_seconds=self._timeout_seconds,
            prompt_version="optimization-lab-ollama-v1",
            expect_json=True,
            response_tag="optimization_lab",
            model_name=model,
            max_tokens=512,
            max_retries=0,
        )
        response = llm_gateway_service.generate(request)
        if response.safe_error:
            raise OptimizationLabError(
                "local_ollama_analysis_failed",
                details={
                    "provider": "ollama",
                    "model": response.model or model,
                    "reason": response.safe_error or "schema_validation_failed",
                },
            )
        try:
            return _normalize_analyzer_result(response.parsed)
        except OptimizationLabError as exc:
            raise OptimizationLabError(
                "local_ollama_analysis_failed",
                details={
                    "provider": "ollama",
                    "model": response.model or model,
                    "reason": exc.code,
                    **exc.details,
                },
            ) from exc


class AnalyzerRegistry:
    def __init__(
        self,
        *,
        analyzers: dict[str, Analyzer] | None = None,
        local_model: str = "",
        local_ready: bool | None = None,
    ):
        configured_model = str(local_model or "").strip()
        if not configured_model:
            try:
                from modules.operations._llm_routing import local_model as configured_local_model

                configured_model = str(configured_local_model() or "").strip()
            except Exception:
                configured_model = ""
        self._local_model = configured_model
        self._local_ready = bool(configured_model) if local_ready is None else bool(local_ready)
        self._analyzers = analyzers or {
            "synthetic": SyntheticAnalyzer(),
            "ollama": OllamaAnalyzer(),
        }

    def profiles(self) -> list[AnalyzerProfile]:
        profiles = [
            AnalyzerProfile(
                profile_id="synthetic",
                provider="synthetic",
                version="synthetic-rule-2026.1",
                ready=True,
                models=("synthetic-rule-v1",),
                efforts=("standard",),
                data_scopes=("synthetic_only",),
            ),
        ]
        profiles.append(
            AnalyzerProfile(
                profile_id="ollama",
                provider="Ollama",
                version="local-gateway-v1",
                ready=self._local_ready and "ollama" in self._analyzers,
                models=(self._local_model,) if self._local_ready and self._local_model else (),
                efforts=("standard",),
                data_scopes=("synthetic_only", "customer_evidence"),
                reason=(
                    "local_ollama_unavailable"
                    if not self._local_ready
                    else ("local_ollama_analyzer_unavailable" if "ollama" not in self._analyzers else "")
                ),
            )
        )
        # These profiles are intentionally visible but not selectable until the
        # real CLI, version probe and automation credential are mounted.
        for profile_id, provider in (("codex", "Codex"), ("claude", "Claude"), ("grok", "Grok")):
            profiles.append(
                AnalyzerProfile(
                    profile_id=profile_id,
                    provider=provider,
                    version="",
                    ready=False,
                    models=(),
                    efforts=(),
                    data_scopes=("synthetic_only",),
                    reason="provider_credentials_unavailable",
                )
            )
        return profiles

    def select(self, *, profile_id: str, model: str, effort: str, data_scope: str) -> tuple[AnalyzerProfile, Analyzer]:
        profile = next((row for row in self.profiles() if row.profile_id == profile_id), None)
        if profile is None:
            raise OptimizationLabError("unknown_analyzer_profile")
        if data_scope not in ANALYZER_DATA_SCOPES:
            raise OptimizationLabError("invalid_analyzer_data_scope")
        if data_scope not in profile.data_scopes:
            raise OptimizationLabError("analyzer_data_scope_not_supported")
        if not profile.ready:
            raise OptimizationLabError(profile.reason or "analyzer_not_ready")
        if model not in profile.models:
            raise OptimizationLabError("unsupported_analyzer_model")
        if effort not in profile.efforts:
            raise OptimizationLabError("unsupported_analyzer_effort")
        analyzer = self._analyzers.get(profile_id)
        if analyzer is None:
            raise OptimizationLabError("analyzer_not_ready")
        return profile, analyzer


def _classify_findings(evidence: list[dict[str, Any]], *, offline_accepted: bool) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in evidence:
        failure = str(row.get("failure_type") or "").strip()
        if failure:
            groups.setdefault(failure, []).append(row)
    findings: list[dict[str, Any]] = []
    for failure, rows in sorted(groups.items()):
        if failure == "rag_miss":
            classification = "RAG Knowledge Gap"
        elif failure in {"stt_timeout", "llm_timeout", "tts_timeout", "model_failure"}:
            classification = "Model Capability"
        elif failure in {"prompt_behavior", "format_failure"}:
            classification = "Prompt Behavior"
        elif failure in {"transport_failure", "workflow_failure"}:
            classification = "Product Pipeline"
        else:
            classification = "Insufficient Evidence"
        # A successful voice turn with a RAG miss is the knowledge-gap signal
        # itself; success is contradictory only for runtime failure findings.
        contradictory = failure != "rag_miss" and any(
            row.get("voice_outcome") == "success" for row in evidence if row in rows
        )
        count = len(rows)
        # Synthetic fixtures are allowed to prove reproducibility only when a
        # future offline evaluator explicitly records that result. Merely being
        # synthetic must not turn two examples into a guidance threshold.
        repeated = count >= 3
        level = (
            "Insufficient Evidence" if contradictory else ("Reference Guidance" if repeated else "Observation Signal")
        )
        guidance = None
        if level == "Reference Guidance" and classification != "Insufficient Evidence":
            guidance = (
                "Offline acceptance required before concrete guidance is reusable."
                if not offline_accepted
                else f"Review the {classification} seam against the frozen synthetic evidence."
            )
        findings.append(
            {
                "classification": classification,
                "failure_type": failure,
                "occurrences": count,
                "evidence_level": level,
                "evidence_ids": [str(row["evidence_id"]) for row in rows],
                "guidance": guidance,
                "offline_acceptance": "passed" if offline_accepted else "unverified",
            }
        )
    return findings


def _diagnostic_answer(
    evidence: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    *,
    offline_accepted: bool,
    candidate_available: bool = False,
) -> str:
    if not evidence:
        return "當日沒有可分析的語音互動證據。"
    if not findings:
        return f"已分析 {len(evidence)} 筆語音互動，目前沒有可歸類的問題。"
    if any(finding["evidence_level"] == "Observation Signal" for finding in findings):
        return f"已分析 {len(evidence)} 筆語音互動，先列為觀察訊號；目前證據不足以提出變更建議。"
    if not offline_accepted:
        return f"已分析 {len(evidence)} 筆語音互動，發現重複模式，但尚未通過離線驗證，暫不提供變更建議。"
    if candidate_available:
        return f"已分析 {len(evidence)} 筆語音互動，發現可處理的 RAG 知識缺口。需要我幫你將分析結果加入 RAG 嗎？"
    return f"已分析 {len(evidence)} 筆語音互動，找到可進一步處理的重複模式。"


def _optimization_evidence(row: dict[str, Any]) -> dict[str, Any]:
    """Translate the Voice Evidence capability contract into analyzer input."""

    terminal_status = str(row.get("terminal_status") or "unknown")
    rag_outcome = str(row.get("rag_outcome") or "not_run")
    failure_type = str(row.get("failure_type") or "")
    if not failure_type and rag_outcome == "miss":
        failure_type = "rag_miss"
    return {
        "evidence_id": str(row.get("evidence_id") or ""),
        "observed_at": str(row.get("observed_at") or ""),
        "transcript_masked": str(row.get("transcript_masked") or "")[:500],
        "assistant_text_masked": str(row.get("assistant_text_masked") or "")[:500],
        "rag_hit": {"hit": rag_outcome == "hit", "outcome": rag_outcome},
        "rag_outcome": rag_outcome,
        "voice_outcome": "success" if terminal_status == "completed" else "failed",
        "failure_type": failure_type,
        "retry_outcome": str(row.get("retry_outcome") or "none"),
        "projection_status": str(row.get("projection_status") or "projected"),
    }


def _effective_rag_outcome(row: dict[str, Any]) -> str:
    outcome = str(row.get("rag_outcome") or "").lower()
    if outcome in {"hit", "miss", "not_run"}:
        return outcome
    legacy = row.get("rag_hit")
    if isinstance(legacy, dict) and "hit" in legacy:
        return "hit" if bool(legacy.get("hit")) else "miss"
    return "not_run"


class OptimizationLabModule:
    def __init__(
        self,
        *,
        store: OptimizationStore,
        analyzers: AnalyzerRegistry | None = None,
        offline_evaluator: OfflineEvaluator | None = None,
        provider_authorization: ProviderAuthorization | None = None,
        knowledge: KnowledgePort | None = None,
        evidence_capability: VoiceEvidenceCapability | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._store = store
        self._analyzers = analyzers or AnalyzerRegistry()
        self._offline = offline_evaluator or NeverAcceptedOfflineEvaluator()
        self._authorization = provider_authorization or DenyProviderAuthorization()
        self._knowledge = knowledge
        self._evidence_capability = evidence_capability
        self._clock = clock or _now

    def profiles(self) -> list[dict[str, Any]]:
        return [profile.as_dict() for profile in self._analyzers.profiles()]

    def list_diagnostic_questions(self, *, scope: CommercialScope) -> list[dict[str, Any]]:
        tenant_id, store_id = _scope_ids(scope)
        self._store.ensure_default_diagnostic_question(
            scope=scope,
            record={
                "question_id": f"diagnostic_default_{tenant_id}_{store_id}",
                "display_name": _DEFAULT_DIAGNOSTIC_QUESTION_NAME,
                "prompt": _DEFAULT_DIAGNOSTIC_QUESTION_PROMPT,
                "created_at": _iso(self._clock()),
                "updated_at": _iso(self._clock()),
            },
        )
        return self._store.list_diagnostic_questions(scope=scope)

    def create_diagnostic_question(self, *, scope: CommercialScope, display_name: str, prompt: str) -> dict[str, Any]:
        display_name, prompt = _diagnostic_question_fields(display_name, prompt)
        now = _iso(self._clock())
        return self._store.create_diagnostic_question(
            scope=scope,
            record={
                "question_id": f"diagnostic_{uuid4().hex}",
                "display_name": display_name,
                "prompt": prompt,
                "created_at": now,
                "updated_at": now,
            },
        )

    def update_diagnostic_question(
        self,
        *,
        scope: CommercialScope,
        question_id: str,
        display_name: str,
        prompt: str,
    ) -> dict[str, Any]:
        display_name, prompt = _diagnostic_question_fields(display_name, prompt)
        updated = self._store.update_diagnostic_question(
            scope=scope,
            question_id=str(question_id),
            record={"display_name": display_name, "prompt": prompt, "updated_at": _iso(self._clock())},
        )
        if updated is None:
            raise OptimizationLabError("diagnostic_question_not_found")
        return updated

    def delete_diagnostic_question(self, *, scope: CommercialScope, question_id: str) -> None:
        if not self._store.delete_diagnostic_question(scope=scope, question_id=str(question_id)):
            raise OptimizationLabError("diagnostic_question_not_found")

    def ingest_evidence(self, *, scope: CommercialScope, payload: dict[str, Any], synthetic: bool) -> dict[str, Any]:
        raw = dict(payload or {})
        forbidden = sorted(key for key in raw if str(key).lower().replace("-", "_") in _FORBIDDEN_KEYS)
        if forbidden:
            raise OptimizationLabError("raw_or_identity_field_not_allowed", details={"fields": forbidden})
        if not synthetic and not str(raw.get("source") or "").strip():
            raise OptimizationLabError("sanitized_source_required")
        observed = _parse_datetime(raw.get("observed_at"))
        failure = _text(raw.get("failure_type"), limit=80).lower()
        if failure not in _SAFE_FAILURES:
            raise OptimizationLabError("invalid_failure_type")
        voice_outcome = _text(raw.get("voice_outcome"), limit=40).lower() or "unknown"
        retry_outcome = _text(raw.get("retry_outcome"), limit=40).lower() or "none"
        if voice_outcome not in _SAFE_VOICE_OUTCOMES:
            raise OptimizationLabError("invalid_voice_outcome")
        if retry_outcome not in _SAFE_RETRY_OUTCOMES:
            raise OptimizationLabError("invalid_retry_outcome")
        record = {
            "evidence_id": f"vie_{uuid4().hex}",
            "observed_at": _iso(observed),
            "transcript_masked": _redact(_text(raw.get("transcript"))),
            "assistant_text_masked": _redact(_text(raw.get("assistant_text"))),
            "rag_hit": _safe_rag_hit(raw.get("rag_hit")),
            "voice_outcome": voice_outcome,
            "failure_type": failure,
            "retry_outcome": retry_outcome,
            "synthetic": bool(synthetic),
            "source": "synthetic_fixture" if synthetic else _text(raw.get("source"), limit=80),
            "created_at": _iso(self._clock()),
            "expires_at": _iso(self._clock() + timedelta(days=30)),
        }
        return self._store.create_evidence(scope=scope, record=record)

    def simulate(
        self,
        *,
        scope: CommercialScope,
        store_date: str,
        timezone_name: str,
        profile_id: str,
        model: str,
        effort: str,
        data_scope: str = "synthetic_only",
        question_id: str | None = None,
    ) -> dict[str, Any]:
        pending_candidate = self._store.get_pending_candidate(scope=scope)
        if pending_candidate is not None:
            raise OptimizationLabError("pending_candidate_requires_abandonment")
        if question_id:
            question = self._store.get_diagnostic_question(scope=scope, question_id=str(question_id))
        else:
            questions = self.list_diagnostic_questions(scope=scope)
            question = questions[0] if questions else None
        if question is None:
            raise OptimizationLabError("diagnostic_question_not_found")
        try:
            selected_date = date.fromisoformat(str(store_date))
            zone = ZoneInfo(str(timezone_name))
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise OptimizationLabError("invalid_store_date_or_timezone") from exc
        now = self._clock().astimezone(timezone.utc)
        local_now = now.astimezone(zone)
        if selected_date > local_now.date():
            raise OptimizationLabError("future_store_date_not_allowed")
        start_local = datetime.combine(selected_date, time.min, tzinfo=zone)
        end_local = start_local + timedelta(days=1)
        is_current = selected_date == local_now.date()
        cutoff = now if is_current else end_local.astimezone(timezone.utc)
        profile, analyzer = self._analyzers.select(
            profile_id=profile_id,
            model=model,
            effort=effort,
            data_scope=data_scope,
        )
        authorization_id = ""
        if data_scope == "customer_evidence" and profile.provider not in {"Ollama", "synthetic"}:
            authorization_id = self._authorization.authorize(
                scope=scope,
                profile=profile,
                model=model,
                effort=effort,
            )
        start_at = _iso(start_local.astimezone(timezone.utc))
        end_at = _iso(end_local.astimezone(timezone.utc))
        if data_scope == "customer_evidence" and self._evidence_capability is not None:
            reconciliation = self._evidence_capability.reconciliation(
                scope=scope,
                observed_from=start_at,
                observed_to=end_at,
            )
            evidence = [
                _optimization_evidence(row)
                for row in self._evidence_capability.snapshot(
                    scope=scope,
                    observed_from=start_at,
                    observed_to=end_at,
                    cutoff_at=_iso(cutoff),
                )
            ]
        else:
            evidence = self._store.list_evidence(
                scope=scope,
                start_at=start_at,
                end_at=end_at,
                cutoff_at=_iso(cutoff),
                synthetic_only=data_scope == "synthetic_only",
            )
            reconciliation = {
                "status": "ready" if evidence else "true_zero",
                "backend_accepted": len(evidence),
                "found": len(evidence),
                "adopted": len(evidence),
                "excluded": 0,
                "awaiting_projection": 0,
                "permanent_projection_failure": 0,
            }
        snapshot = self._store.create_snapshot(
            scope=scope,
            record={
                "snapshot_id": f"snap_{uuid4().hex}",
                "store_date": selected_date.isoformat(),
                "timezone": str(timezone_name),
                "cutoff_at": _iso(cutoff),
                "partial": is_current,
                "evidence_ids": [str(row["evidence_id"]) for row in evidence],
                "created_at": _iso(now),
                "expires_at": _iso(now + timedelta(days=30)),
            },
        )
        analysis_snapshot = {
            **snapshot,
            "diagnostic_question": {
                "question_id": str(question["question_id"]),
                "display_name": str(question["display_name"]),
                "prompt": str(question["prompt"]),
            },
            "evidence": evidence,
        }
        analyzer_result = analyzer.analyze(snapshot=analysis_snapshot, profile=profile)
        offline_accepted = bool(self._offline.evaluate(snapshot=analysis_snapshot))
        findings = _classify_findings(evidence, offline_accepted=offline_accepted)
        question_snapshot = {
            "question_id": str(question["question_id"]),
            "display_name": str(question["display_name"]),
            "prompt": str(question["prompt"]),
        }
        candidate = self._build_knowledge_candidate(
            scope=scope,
            report_id=f"report_{uuid4().hex}",
            question=question_snapshot,
            findings=findings,
            offline_accepted=offline_accepted,
            now=now,
        )
        report = {
            "report_id": candidate["report_id"] if candidate else f"report_{uuid4().hex}",
            "snapshot_id": snapshot["snapshot_id"],
            "store_date": selected_date.isoformat(),
            "timezone": str(timezone_name),
            "partial": is_current,
            "analyzer": profile.as_dict(),
            "selected_model": model,
            "selected_effort": effort,
            "data_scope": data_scope,
            "evidence_count": len(evidence),
            "evidence_summary": {
                **reconciliation,
                "count": len(evidence),
                "level": (
                    next((finding["evidence_level"] for finding in findings if finding.get("evidence_level")), None)
                    or ("No Evidence" if reconciliation["status"] == "true_zero" else reconciliation["status"])
                ),
            },
            "evidence_ids": [str(row["evidence_id"]) for row in evidence],
            "diagnostic_question": question_snapshot,
            "dialogue": {
                "question": question_snapshot["prompt"],
                "answer": _diagnostic_answer(
                    evidence,
                    findings,
                    offline_accepted=offline_accepted,
                    candidate_available=bool(candidate),
                ),
            },
            "sections": [
                {
                    "id": "api_connectivity",
                    "data": _bounded_metrics(
                        analyzer_result.get("api_connectivity"),
                        numeric_keys=("evidence_count",),
                        text_keys=("status",),
                    ),
                },
                {
                    "id": "commercial_outcomes",
                    "data": _bounded_metrics(
                        analyzer_result.get("commercial_outcomes"),
                        numeric_keys=("voice_evidence_count",),
                    ),
                },
                {
                    "id": "voice_outcomes",
                    "data": _bounded_metrics(
                        analyzer_result.get("voice_outcomes"),
                        numeric_keys=("completed", "failed", "retry_or_correction"),
                    ),
                },
                {
                    "id": "rag_observations",
                    "data": _bounded_metrics(
                        analyzer_result.get("rag_observations"),
                        numeric_keys=("hits", "misses"),
                    ),
                },
                {
                    "id": "voice_interaction_analysis",
                    "data": {"evidence_count": len(evidence), "identifiers": "opaque_only"},
                },
                {
                    "id": "findings_and_guidance",
                    "data": {
                        "findings": findings,
                        "offline_acceptance": "passed" if offline_accepted else "unverified",
                    },
                },
            ],
            "created_at": _iso(now),
            "expires_at": _iso(now + timedelta(days=30)),
            "status": "partial" if is_current else "complete",
        }
        stored = self._store.save_report(scope=scope, record=report)
        if candidate:
            self._store.create_candidate(scope=scope, record=candidate)
            report["knowledge_change_candidate"] = candidate
            stored = self._store.update_report(scope=scope, report_id=stored["report_id"], record=report)
        if data_scope == "customer_evidence":
            self._store.record_egress_audit(
                scope=scope,
                record={
                    "audit_id": f"egress_{uuid4().hex}",
                    "report_id": stored["report_id"],
                    "analyzer_id": profile.profile_id,
                    "analyzer_version": profile.version,
                    "model": model,
                    "effort": effort,
                    "data_scope": data_scope,
                    "evidence_count": len(evidence),
                    "evidence_ids": [str(row["evidence_id"]) for row in evidence],
                    "authorization_id": authorization_id,
                    "observed_at": _iso(now),
                },
            )
        return stored

    def _build_knowledge_candidate(
        self,
        *,
        scope: CommercialScope,
        report_id: str,
        question: dict[str, str],
        findings: list[dict[str, Any]],
        offline_accepted: bool,
        now: datetime,
    ) -> dict[str, Any] | None:
        eligible = next(
            (
                finding
                for finding in findings
                if finding.get("classification") == "RAG Knowledge Gap"
                and finding.get("evidence_level") == "Reference Guidance"
                and finding.get("offline_acceptance") == "passed"
            ),
            None,
        )
        if eligible is None:
            return None
        items = []
        if self._knowledge is not None:
            items = list((self._knowledge.list_items(scope=scope) or {}).get("items") or [])
        failure = str(eligible.get("failure_type") or "rag_miss")
        existing = next(
            (
                item
                for item in items
                if failure in str(item.get("content") or "").lower()
                or question["prompt"] in str(item.get("content") or "")
            ),
            None,
        )
        proposed = {
            "title": f"{question['display_name']}：{failure}",
            "category": "other",
            "content_type": "question_answer",
            "content": (
                f"問題：{question['prompt']}\n\n"
                f"觀察：在 {eligible['occurrences']} 筆語音互動中出現 {failure}。\n\n"
                "建議：請補充可供門市知識庫檢索的正式答案，並由管理員確認後發布。"
            ),
        }
        return {
            "candidate_id": f"candidate_{uuid4().hex}",
            "report_id": report_id,
            "status": "pending",
            "action": "update" if existing else "create",
            "target_item_id": str(existing.get("item_id")) if existing else None,
            "expected_row_revision": existing.get("row_revision") if existing else None,
            "existing": {
                key: existing.get(key)
                for key in ("item_id", "row_revision", "title", "category", "content_type", "content")
            }
            if existing
            else None,
            "proposed": proposed,
            "offline_acceptance": "passed",
            "evidence_ids": list(eligible.get("evidence_ids") or []),
            "created_at": _iso(now),
            "expires_at": _iso(now + timedelta(days=30)),
        }

    def get_report(self, *, scope: CommercialScope, report_id: str) -> dict[str, Any]:
        report = self._store.get_report(scope=scope, report_id=report_id)
        if report is None:
            raise OptimizationLabError("report_not_found")
        return report

    def latest_report(self, *, scope: CommercialScope) -> dict[str, Any] | None:
        return self._store.latest_report(scope=scope)

    def pending_candidate(self, *, scope: CommercialScope) -> dict[str, Any] | None:
        return self._store.get_pending_candidate(scope=scope)

    def abandon_candidate(self, *, scope: CommercialScope, candidate_id: str) -> dict[str, Any]:
        candidate = self._store.get_candidate(scope=scope, candidate_id=str(candidate_id))
        if candidate is None or candidate.get("status") != "pending":
            raise OptimizationLabError("knowledge_candidate_not_found")
        abandoned = {**candidate, "status": "abandoned", "abandoned_at": _iso(self._clock())}
        updated = self._store.update_candidate(scope=scope, candidate_id=str(candidate_id), record=abandoned)
        if updated is None:
            raise OptimizationLabError("knowledge_candidate_not_found")
        return updated

    def edit_candidate(
        self,
        *,
        scope: CommercialScope,
        candidate_id: str,
        title: str,
        category: str,
        content_type: str,
        content: str,
    ) -> dict[str, Any]:
        candidate = self._store.get_candidate(scope=scope, candidate_id=str(candidate_id))
        if candidate is None or candidate.get("status") != "pending":
            raise OptimizationLabError("knowledge_candidate_not_found")
        values = {
            "title": _text(title, limit=160),
            "category": _text(category, limit=64),
            "content_type": _text(content_type, limit=64),
            "content": _text(content, limit=200_000),
        }
        if not all(values.values()):
            raise OptimizationLabError("knowledge_candidate_fields_required")
        evidence = [
            self._store.get_evidence(scope=scope, evidence_id=evidence_id)
            for evidence_id in candidate.get("evidence_ids") or []
        ]
        accepted = bool(
            self._offline.evaluate(
                snapshot={"candidate": values, "evidence": [row for row in evidence if row is not None]}
            )
        )
        updated = {
            **candidate,
            "proposed": values,
            "offline_acceptance": "passed" if accepted else "unverified",
            "edited_at": _iso(self._clock()),
        }
        saved = self._store.update_candidate(scope=scope, candidate_id=str(candidate_id), record=updated)
        if saved is None:
            raise OptimizationLabError("knowledge_candidate_not_found")
        return saved

    def confirm_candidate(self, *, scope: CommercialScope, candidate_id: str, actor: str) -> dict[str, Any]:
        candidate = self._store.get_candidate(scope=scope, candidate_id=str(candidate_id))
        if candidate is None or candidate.get("status") != "pending":
            raise OptimizationLabError("knowledge_candidate_not_found")
        if candidate.get("offline_acceptance") != "passed":
            raise OptimizationLabError("knowledge_candidate_not_accepted")
        if self._knowledge is None:
            raise OptimizationLabError("knowledge_publication_unavailable")
        proposed = dict(candidate.get("proposed") or {})
        try:
            if candidate.get("action") == "update":
                item_id = str(candidate.get("target_item_id") or "")
                current = self._knowledge.get_item(scope=scope, item_id=item_id)
                if current.get("row_revision") != candidate.get("expected_row_revision"):
                    stale = {**candidate, "status": "stale", "stale_at": _iso(self._clock())}
                    self._store.update_candidate(scope=scope, candidate_id=str(candidate_id), record=stale)
                    raise OptimizationLabError("knowledge_candidate_stale")
                raw_item = self._knowledge.revise_draft(
                    scope=scope,
                    item_id=item_id,
                    expected_row_revision=int(candidate["expected_row_revision"]),
                    category=proposed["category"],
                    content_type=proposed["content_type"],
                    title=proposed["title"],
                    content=proposed["content"],
                    actor=actor,
                )
            else:
                raw_item = self._knowledge.create_draft(
                    scope=scope,
                    category=proposed["category"],
                    content_type=proposed["content_type"],
                    title=proposed["title"],
                    content=proposed["content"],
                    actor=actor,
                )
            item = {
                key: raw_item.get(key)
                for key in ("item_id", "row_revision", "title", "category", "content_type", "status")
                if key in raw_item
            }
            publication = self._knowledge.request_publication(
                scope=scope, item_ids=[str(item["item_id"])], actor=actor, retry_failures_only=False
            )
        except OptimizationLabError:
            raise
        except Exception as exc:
            raise OptimizationLabError("knowledge_publication_failed") from exc
        confirmed = {
            **candidate,
            "status": "confirmed",
            "confirmed_at": _iso(self._clock()),
            "knowledge_item": item,
            "publication": publication,
        }
        saved = self._store.update_candidate(scope=scope, candidate_id=str(candidate_id), record=confirmed)
        if saved is None:
            raise OptimizationLabError("knowledge_candidate_not_found")
        return saved

    def expand_evidence(
        self,
        *,
        scope: CommercialScope,
        report_id: str,
        evidence_id: str,
        actor: str,
        step_up_valid_until: datetime | None,
    ) -> dict[str, Any]:
        if not step_up_valid_until or step_up_valid_until <= self._clock():
            raise OptimizationLabError("step_up_required")
        report = self.get_report(scope=scope, report_id=report_id)
        if evidence_id not in set(report.get("evidence_ids") or []):
            raise OptimizationLabError("evidence_not_in_report")
        evidence = self._store.get_evidence(scope=scope, evidence_id=evidence_id)
        if evidence is None:
            raise OptimizationLabError("evidence_expired")
        self._store.record_access_audit(
            scope=scope,
            record={
                "audit_id": f"access_{uuid4().hex}",
                "report_id": report_id,
                "evidence_id": evidence_id,
                "actor": str(actor or "admin"),
                "step_up_expires_at": _iso(step_up_valid_until),
                "observed_at": _iso(self._clock()),
            },
        )
        return {
            "evidence_id": evidence["evidence_id"],
            "observed_at": evidence["observed_at"],
            "transcript_masked": evidence["transcript_masked"],
            "assistant_text_masked": evidence["assistant_text_masked"],
            "rag_hit": evidence["rag_hit"],
            "voice_outcome": evidence["voice_outcome"],
            "failure_type": evidence["failure_type"],
            "retry_outcome": evidence["retry_outcome"],
        }

    def cleanup_expired(self) -> int:
        return self._store.cleanup_expired(now=_iso(self._clock()))
