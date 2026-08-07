"""Multimodal evidence gateway — R1-Omni isolation."""

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


def configured_provider_status(timeout_seconds: float = 1.5) -> dict:
    """Return a safe readiness view for the fixed R1-Omni runtime."""
    provider = "r1_omni"
    base_url = str(config.R1_OMNI_GRADIO_URL)
    started = time.perf_counter()
    try:
        response = httpx.get(base_url.rstrip("/") + "/health", timeout=max(0.1, timeout_seconds))
        response.raise_for_status()
        body = response.json() if response.content else {}
        model_loaded = bool(body.get("model_loaded", False)) if isinstance(body, dict) else False
        declared_capabilities = body.get("capabilities", []) if isinstance(body, dict) else []
        capabilities = [str(value) for value in declared_capabilities if str(value)]
        if not capabilities:
            capabilities = ["video_audio"]
        ready = bool(isinstance(body, dict) and body.get("status") == "ok" and model_loaded)
        result = {
            "provider": provider,
            "status": "ready" if ready else "unavailable",
            "model_loaded": model_loaded,
            "capabilities": capabilities,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        if not ready:
            result["message"] = "R1-Omni 服務可連線，但模型尚未載入完成。"
        return result
    except Exception:
        return {
            "provider": provider,
            "status": "unavailable",
            "model_loaded": False,
            "capabilities": [],
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "message": "R1-Omni 服務未就緒，請使用 Docker Compose 檢查或重新啟動 r1-omni 服務。",
        }


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
            status="disabled",
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
    """Call the production R1-Omni `/predict` contract.

    Only adapters may perform provider HTTP. Application services must use
    `collect_evidence` instead of calling provider URLs directly.
    """

    started = time.perf_counter()
    endpoint = url.rstrip("/") + "/predict"
    try:
        with httpx.Client(timeout=max(0.1, float(request.timeout_seconds))) as client:
            response = client.post(
                endpoint,
                json={
                    "video_path": request.media_path,
                    "question": request.question,
                    "skip_quality_check": request.skip_quality_check,
                    "media_mode": request.media_mode,
                },
            )
            response.raise_for_status()
            body = response.json() if response.content else {}
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
            safe_metadata={"event_type": request.event_type},
            safe_error=_safe_error(str(exc)),
            has_evidence=False,
            status="error",
        )
    latency_ms = (time.perf_counter() - started) * 1000.0
    if not isinstance(body, dict):
        body = {"result": str(body)}
    # Production servers return {"result": <str|dict>}
    raw_result = body.get("result", body)
    if isinstance(raw_result, dict):
        payload = raw_result
        text = str(payload.get("description") or payload.get("raw") or "")
    else:
        text = str(raw_result or "")
        payload = {"description": text}
        try:
            import json as _json

            parsed = _json.loads(text)
            if isinstance(parsed, dict):
                payload = parsed
                text = str(payload.get("description") or text)
        except Exception:
            pass
    if text.startswith("[R1_OMNI_SKIP]"):
        return MultimodalEvidence(
            provider=provider,
            model_version=model_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=None,
            signals={},
            quality="skipped",
            latency_ms=latency_ms,
            safe_metadata={"reason": "quality_skip", "event_type": request.event_type},
            safe_error="",
            has_evidence=False,
            status="skipped",
        )
    if text.startswith("[R1_OMNI_ERROR]"):
        return MultimodalEvidence(
            provider=provider,
            model_version=model_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=None,
            signals={},
            quality="error",
            latency_ms=latency_ms,
            safe_metadata={"event_type": request.event_type},
            safe_error="provider_returned_error",
            has_evidence=False,
            status="error",
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
    quality = "ok" if has_evidence else "low_confidence"
    return MultimodalEvidence(
        provider=provider,
        model_version=model_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        confidence=confidence_f,
        signals=signals,
        quality=quality,
        latency_ms=latency_ms,
        safe_metadata={
            "event_type": request.event_type,
            "prompt_version": request.prompt_version,
            **dict(request.scope_safe_metadata or {}),
        },
        safe_error="",
        has_evidence=has_evidence,
        status="ok" if has_evidence else "no_evidence",
    )


def default_adapters() -> dict[str, MultimodalEvidencePort]:
    return {
        "r1_omni": R1OmniAdapter(),
        "null": NullEvidenceAdapter(),
    }


def collect_evidence(
    request: MultimodalEvidenceRequest,
    *,
    adapters: Mapping[str, MultimodalEvidencePort] | None = None,
    enabled: bool | None = None,
) -> MultimodalEvidence:
    """Return multimodal evidence only — never a transaction decision."""

    registry = dict(adapters or default_adapters())
    if enabled is None:
        enabled = bool(config.get("EMOTION_ENABLED", False))
    if not enabled:
        evidence = registry["null"].analyze(request)
        _metric("null", "disabled")
        return evidence

    provider_name = "r1_omni"
    adapter = registry.get(provider_name)
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
