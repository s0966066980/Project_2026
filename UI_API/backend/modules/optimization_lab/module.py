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


class OptimizationStore(Protocol):
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

    def get_report(self, *, scope: CommercialScope, report_id: str) -> dict[str, Any] | None: ...

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
        rag_hits = sum(1 for row in evidence if bool((row.get("rag_hit") or {}).get("hit")))
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
            "rag_observations": {"hits": rag_hits, "misses": max(0, len(evidence) - rag_hits)},
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
                "values. Never return transcript, assistant text, identifiers, recommendations, "
                "prompts, settings, or production mutations."
            ),
            user_prompt=json.dumps(
                {
                    "store_date": snapshot.get("store_date"),
                    "timezone": snapshot.get("timezone"),
                    "partial": bool(snapshot.get("partial")),
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
                data_scopes=("synthetic_only",),
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
        contradictory = any(row.get("voice_outcome") == "success" for row in evidence if row in rows)
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


class OptimizationLabModule:
    def __init__(
        self,
        *,
        store: OptimizationStore,
        analyzers: AnalyzerRegistry | None = None,
        offline_evaluator: OfflineEvaluator | None = None,
        provider_authorization: ProviderAuthorization | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._store = store
        self._analyzers = analyzers or AnalyzerRegistry()
        self._offline = offline_evaluator or NeverAcceptedOfflineEvaluator()
        self._authorization = provider_authorization or DenyProviderAuthorization()
        self._clock = clock or _now

    def profiles(self) -> list[dict[str, Any]]:
        return [profile.as_dict() for profile in self._analyzers.profiles()]

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
    ) -> dict[str, Any]:
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
        if data_scope == "customer_evidence":
            authorization_id = self._authorization.authorize(
                scope=scope,
                profile=profile,
                model=model,
                effort=effort,
            )
        evidence = self._store.list_evidence(
            scope=scope,
            start_at=_iso(start_local.astimezone(timezone.utc)),
            end_at=_iso(end_local.astimezone(timezone.utc)),
            cutoff_at=_iso(cutoff),
            synthetic_only=data_scope == "synthetic_only",
        )
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
        analyzer_result = analyzer.analyze(snapshot={**snapshot, "evidence": evidence}, profile=profile)
        offline_accepted = bool(self._offline.evaluate(snapshot={**snapshot, "evidence": evidence}))
        findings = _classify_findings(evidence, offline_accepted=offline_accepted)
        report = {
            "report_id": f"report_{uuid4().hex}",
            "snapshot_id": snapshot["snapshot_id"],
            "store_date": selected_date.isoformat(),
            "timezone": str(timezone_name),
            "partial": is_current,
            "analyzer": profile.as_dict(),
            "selected_model": model,
            "selected_effort": effort,
            "data_scope": data_scope,
            "evidence_count": len(evidence),
            "evidence_ids": [str(row["evidence_id"]) for row in evidence],
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

    def get_report(self, *, scope: CommercialScope, report_id: str) -> dict[str, Any]:
        report = self._store.get_report(scope=scope, report_id=report_id)
        if report is None:
            raise OptimizationLabError("report_not_found")
        return report

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
