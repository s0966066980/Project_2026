"""Multimodal evidence gateway — Emotion-LLaMA / R1-Omni isolation."""

from __future__ import annotations

import concurrent.futures
import time
from datetime import datetime, timezone
from typing import Mapping

import httpx

import config
from models.multimodal_evidence import (
    MultimodalEvidence,
    MultimodalEvidencePort,
    MultimodalEvidenceRequest,
)
from services import observability_service


def _safe_error(text: str) -> str:
    return observability_service.redact_sensitive_text(text)[:300]


def _metric(provider: str, status: str) -> None:
    observability_service.increment_metric("emotion_evidence_total", status=f"{provider}_{status}"[:80])


class NullEvidenceAdapter:
    """Always returns no evidence; used when models are disabled or unavailable."""

    name = "null"

    def analyze(self, request: MultimodalEvidenceRequest) -> MultimodalEvidence:
        return MultimodalEvidence(
            provider=self.name,
            model_version="null",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=None,
            signals={},
            quality="unavailable",
            latency_ms=0.0,
            safe_metadata={"reason": "null_adapter"},
            safe_error="",
            has_evidence=False,
        )


class EmotionLlamaAdapter:
    name = "emotion_llama"

    def analyze(self, request: MultimodalEvidenceRequest) -> MultimodalEvidence:
        return _http_provider_analyze(
            provider=self.name,
            url=str(config.EMOTION_LLAMA_GRADIO_URL),
            request=request,
            model_version=str(config.get("EMOTION_LLAMA_MODEL_VERSION", "emotion-llama")),
        )


class R1OmniAdapter:
    name = "r1_omni"

    def analyze(self, request: MultimodalEvidenceRequest) -> MultimodalEvidence:
        return _http_provider_analyze(
            provider=self.name,
            url=str(config.R1_OMNI_GRADIO_URL),
            request=request,
            model_version=str(config.get("R1_OMNI_MODEL_VERSION", "r1-omni")),
        )


def _http_provider_analyze(
    *,
    provider: str,
    url: str,
    request: MultimodalEvidenceRequest,
    model_version: str,
) -> MultimodalEvidence:
    started = time.perf_counter()
    endpoint = url.rstrip("/") + "/analyze"
    try:
        with httpx.Client(timeout=max(0.1, float(request.timeout_seconds))) as client:
            response = client.post(
                endpoint,
                json={
                    "media_path": request.media_path,
                    "question": request.question,
                    "skip_quality_check": request.skip_quality_check,
                },
            )
            response.raise_for_status()
            payload = (
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {"description": response.text}
            )
    except Exception as exc:  # noqa: BLE001 - adapter boundary
        latency_ms = (time.perf_counter() - started) * 1000.0
        return MultimodalEvidence(
            provider=provider,
            model_version=model_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=None,
            signals={},
            quality="error",
            latency_ms=latency_ms,
            safe_metadata={},
            safe_error=_safe_error(str(exc)),
            has_evidence=False,
        )
    latency_ms = (time.perf_counter() - started) * 1000.0
    if not isinstance(payload, dict):
        payload = {"description": str(payload)}
    text = str(payload.get("description") or payload.get("raw") or "")
    if text.startswith("[EMOTION_LLAMA_SKIP]"):
        return MultimodalEvidence(
            provider=provider,
            model_version=model_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=None,
            signals={},
            quality="skipped",
            latency_ms=latency_ms,
            safe_metadata={"reason": "quality_skip"},
            safe_error="",
            has_evidence=False,
        )
    if text.startswith("[EMOTION_LLAMA_ERROR]"):
        return MultimodalEvidence(
            provider=provider,
            model_version=model_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=None,
            signals={},
            quality="error",
            latency_ms=latency_ms,
            safe_metadata={},
            safe_error="provider_returned_error",
            has_evidence=False,
        )
    signals = {
        "emotion": str(payload.get("emotion") or ""),
        "intensity": str(payload.get("intensity") or ""),
        "facial": str(payload.get("facial") or ""),
        "vocal": str(payload.get("vocal") or ""),
        "description": text or str(payload.get("description") or ""),
    }
    confidence = payload.get("confidence")
    try:
        confidence_f = float(confidence) if confidence is not None and str(confidence) != "" else None
    except (TypeError, ValueError):
        confidence_f = None
    has_evidence = bool(signals.get("emotion") or signals.get("description"))
    return MultimodalEvidence(
        provider=provider,
        model_version=model_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        confidence=confidence_f,
        signals=signals,
        quality="ok" if has_evidence else "low_confidence",
        latency_ms=latency_ms,
        safe_metadata={"event_type": request.event_type},
        safe_error="",
        has_evidence=has_evidence,
    )


def default_adapters() -> dict[str, MultimodalEvidencePort]:
    return {
        "emotion_llama": EmotionLlamaAdapter(),
        "r1_omni": R1OmniAdapter(),
        "null": NullEvidenceAdapter(),
    }


def _resolve_provider(preference: str) -> str:
    preferred = (preference or config.get("EMOTION_PROVIDER", "emotion_llama") or "emotion_llama").strip()
    if preferred in {"emotion_llama", "r1_omni", "null"}:
        return preferred
    return "emotion_llama"


def collect_evidence(
    request: MultimodalEvidenceRequest,
    *,
    adapters: Mapping[str, MultimodalEvidencePort] | None = None,
    enabled: bool | None = None,
) -> MultimodalEvidence:
    """Return multimodal evidence only — never a transaction decision."""

    registry = dict(adapters or default_adapters())
    if enabled is None:
        enabled = bool(config.get("EMOTION_LLAMA_ENABLED", False))
    if not enabled:
        evidence = registry["null"].analyze(request)
        _metric("null", "disabled")
        return evidence

    provider_name = _resolve_provider(request.provider_preference)
    adapter = registry.get(provider_name)
    if adapter is None:
        for candidate in ("emotion_llama", "r1_omni", "null"):
            if candidate in registry:
                adapter = registry[candidate]
                provider_name = candidate
                break
    if adapter is None:
        adapter = NullEvidenceAdapter()
        provider_name = "null"
    attempts = 0
    max_attempts = max(0, int(request.max_retries)) + 1
    last = MultimodalEvidence(
        provider=provider_name,
        model_version="unknown",
        timestamp=datetime.now(timezone.utc).isoformat(),
        confidence=None,
        signals={},
        quality="unavailable",
        latency_ms=0.0,
        has_evidence=False,
    )
    while attempts < max_attempts:
        attempts += 1
        last = _call_with_timeout(adapter, request)
        if last.has_evidence and last.quality in {"ok", "low_confidence"}:
            _metric(last.provider, last.quality)
            return last
        if last.quality == "skipped":
            _metric(last.provider, "skipped")
            return last
        if attempts < max_attempts and last.safe_error:
            continue
        break
    # Fail open with no evidence — never block checkout/core flows.
    if not last.has_evidence:
        _metric(last.provider or provider_name, "no_evidence")
        return MultimodalEvidence(
            provider=last.provider or provider_name,
            model_version=last.model_version,
            timestamp=last.timestamp,
            confidence=None,
            signals=dict(last.signals or {}),
            quality=last.quality or "unavailable",
            latency_ms=last.latency_ms,
            safe_metadata={"degraded": True, **dict(last.safe_metadata or {})},
            safe_error=last.safe_error,
            has_evidence=False,
        )
    _metric(last.provider, last.quality)
    return last


def _call_with_timeout(adapter: MultimodalEvidencePort, request: MultimodalEvidenceRequest) -> MultimodalEvidence:
    timeout = max(0.001, float(request.timeout_seconds))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(adapter.analyze, request)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return MultimodalEvidence(
                provider=getattr(adapter, "name", "unknown"),
                model_version="unknown",
                timestamp=datetime.now(timezone.utc).isoformat(),
                confidence=None,
                signals={},
                quality="timeout",
                latency_ms=timeout * 1000.0,
                safe_metadata={},
                safe_error="provider_timeout",
                has_evidence=False,
            )
        except Exception as exc:  # noqa: BLE001
            return MultimodalEvidence(
                provider=getattr(adapter, "name", "unknown"),
                model_version="unknown",
                timestamp=datetime.now(timezone.utc).isoformat(),
                confidence=None,
                signals={},
                quality="error",
                latency_ms=0.0,
                safe_metadata={},
                safe_error=_safe_error(str(exc)),
                has_evidence=False,
            )


def evidence_is_not_transaction_authority(evidence: MultimodalEvidence) -> bool:
    """Hard invariant: evidence never authorizes order/payment mutations."""

    return "order_id" not in evidence.signals and "authorize_payment" not in evidence.signals
