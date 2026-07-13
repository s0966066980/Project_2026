"""LLM Gateway: timeout, retry, fallback, metrics, and prompt-version contract."""

from __future__ import annotations

import concurrent.futures
import json
import time
from typing import Any, Mapping

from models.llm import (
    LLMAdapterResult,
    LLMModelPolicy,
    LLMPort,
    LLMRequest,
    LLMResponse,
)
from services import observability_service

_RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "unavailable",
    "503",
    "429",
    "rate",
    "overloaded",
    "cooldown",
    "temporarily",
)

# Long-lived pool so timeout returns without waiting for a stuck worker to finish
# (context-managed ThreadPoolExecutor.__exit__ would block until the thread ends).
_GATEWAY_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="llm-gateway",
)

# Task-level structured output contracts (required keys). Values are further
# validated by the calling application service (menu whitelist, length, etc.).
TASK_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "ai_push_copy": frozenset({"recommendation_id", "push_text"}),
    "voice_assist": frozenset({"ai_response"}),
    "payment_assist": frozenset(),  # free-form assist message fields accepted
    "emotion_extract": frozenset({"emotion", "intensity"}),
}


def _provider_chain(policy: LLMModelPolicy) -> list[str]:
    if policy is LLMModelPolicy.LOCAL_ONLY:
        return ["ollama"]
    if policy is LLMModelPolicy.CLOUD_ONLY:
        return ["gemini"]
    if policy is LLMModelPolicy.CLOUD_FIRST:
        return ["gemini", "ollama"]
    return ["ollama", "gemini"]


def _is_retryable(safe_error: str, explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    text = str(safe_error or "").casefold()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


def _safe_error(text: str) -> str:
    return observability_service.redact_sensitive_text(text)[:300]


def _metric(provider: str, reason: str) -> None:
    label = f"{provider}_{reason}"[:80]
    observability_service.increment_metric("llm_provider_requests_total", status=label)


def _validate_json_content(content: str) -> dict | None:
    text = str(content or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


class OllamaAdapter:
    name = "ollama"

    def generate(self, request: LLMRequest) -> LLMAdapterResult:
        import ai_services

        started = time.perf_counter()
        raw_obj: Any
        if request.expect_json:
            raw_obj = ai_services.ask_ollama(
                request.system_prompt,
                request.user_prompt,
                request.response_tag,
                request.model_name,
                num_predict=request.max_tokens,
            )
        else:
            raw_obj = ai_services.ask_ollama_raw_text(
                request.system_prompt,
                request.user_prompt,
                request.model_name,
            )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not isinstance(raw_obj, dict):
            return LLMAdapterResult(
                content="",
                provider=self.name,
                model=request.model_name or "ollama",
                latency_ms=latency_ms,
                usage=None,
                finish_reason="error",
                safe_error="invalid_provider_payload",
                retryable=True,
                parsed=None,
            )
        raw: dict[str, Any] = raw_obj
        error = str(raw.get("error") or "")
        content = str(raw.get("raw_content") or raw.get("content") or "")
        if error:
            return LLMAdapterResult(
                content=content,
                provider=self.name,
                model=str(raw.get("model") or request.model_name or "ollama"),
                latency_ms=latency_ms,
                usage=None,
                finish_reason="error",
                safe_error=_safe_error(error),
                retryable=_is_retryable(error),
                parsed=None,
            )
        parsed: dict[str, Any] | None = {
            k: v for k, v in raw.items() if not str(k).startswith("_") and k not in {"error", "raw_content"}
        }
        if request.expect_json and not parsed:
            parsed = _validate_json_content(content)
        if request.expect_json and parsed:
            body = content or json.dumps(parsed, ensure_ascii=False)
        else:
            body = content
        return LLMAdapterResult(
            content=body,
            provider=self.name,
            model=str(raw.get("model") or request.model_name or "ollama"),
            latency_ms=latency_ms,
            usage=None,
            finish_reason="stop",
            safe_error="",
            retryable=False,
            parsed=parsed if request.expect_json else None,
        )


class GeminiAdapter:
    name = "gemini"

    def generate(self, request: LLMRequest) -> LLMAdapterResult:
        import ai_services

        started = time.perf_counter()
        raw_obj: Any
        if request.expect_json:
            raw_obj = ai_services.ask_gemini(
                request.system_prompt,
                request.user_prompt,
                request.response_tag,
                request.model_name,
            )
        else:
            raw_obj = ai_services.ask_gemini_raw_text(
                request.system_prompt,
                request.user_prompt,
                request.model_name,
            )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not isinstance(raw_obj, dict):
            return LLMAdapterResult(
                content="",
                provider=self.name,
                model=request.model_name or "gemini",
                latency_ms=latency_ms,
                usage=None,
                finish_reason="error",
                safe_error="invalid_provider_payload",
                retryable=True,
                parsed=None,
            )
        raw: dict[str, Any] = raw_obj
        error = str(raw.get("error") or "")
        content = str(raw.get("raw_content") or raw.get("content") or "")
        if error:
            provider_error = str(raw.get("_provider_error") or error)
            return LLMAdapterResult(
                content=content,
                provider=self.name,
                model=str(raw.get("model") or request.model_name or "gemini"),
                latency_ms=latency_ms,
                usage=None,
                finish_reason="error",
                safe_error=_safe_error(provider_error),
                retryable=_is_retryable(
                    provider_error,
                    explicit=any(
                        marker in provider_error.casefold()
                        for marker in ("cooldown", "rate", "unavailable", "internal")
                    )
                    or None,
                ),
                parsed=None,
            )
        parsed: dict[str, Any] | None = {
            k: v for k, v in raw.items() if not str(k).startswith("_") and k not in {"error", "raw_content"}
        }
        if request.expect_json and not parsed:
            parsed = _validate_json_content(content)
        if request.expect_json and parsed:
            body = content or json.dumps(parsed, ensure_ascii=False)
        else:
            body = content
        return LLMAdapterResult(
            content=body,
            provider=self.name,
            model=str(raw.get("model") or request.model_name or "gemini"),
            latency_ms=latency_ms,
            usage=None,
            finish_reason="stop",
            safe_error="",
            retryable=False,
            parsed=parsed if request.expect_json else None,
        )


def default_adapters() -> dict[str, LLMPort]:
    return {"ollama": OllamaAdapter(), "gemini": GeminiAdapter()}


def parse_structured_content(content: str, tag: str = "") -> dict[str, Any]:
    """Parse provider JSON text via adapter-layer helper (not a production caller import)."""

    import ai_services

    parsed = ai_services.parse_llm_json(content, tag)
    return parsed if isinstance(parsed, dict) else {}


def stream_tokens(
    request: LLMRequest,
    *,
    num_predict: int | None = None,
):
    """Stream tokens through the Ollama adapter path only (Gemini stream not required)."""

    import ai_services

    model = request.model_name or ""
    yield from ai_services.stream_ollama_tokens(
        request.system_prompt,
        request.user_prompt,
        model,
        num_predict if num_predict is not None else request.max_tokens,
    )


def _validate_task_schema(task: str, parsed: dict[str, Any] | None) -> str:
    """Return empty string when valid; otherwise a safe schema error code."""

    required = TASK_REQUIRED_FIELDS.get(str(task or "").strip())
    if required is None:
        return ""
    if not isinstance(parsed, dict):
        return "schema_validation_failed"
    missing = [key for key in required if key not in parsed or parsed.get(key) in (None, "")]
    if missing:
        return "schema_missing_fields"
    return ""


def _call_with_timeout(adapter: LLMPort, request: LLMRequest) -> LLMAdapterResult:
    timeout = max(0.001, float(request.timeout_seconds))
    started = time.perf_counter()
    future = _GATEWAY_EXECUTOR.submit(adapter.generate, request)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        # Do not wait for the underlying provider thread; return within budget.
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return LLMAdapterResult(
            content="",
            provider=getattr(adapter, "name", "unknown"),
            model=request.model_name or getattr(adapter, "name", "unknown"),
            latency_ms=elapsed_ms,
            usage=None,
            finish_reason="timeout",
            safe_error="provider_timeout",
            retryable=True,
            parsed=None,
        )
    except Exception as exc:  # noqa: BLE001 - gateway boundary
        return LLMAdapterResult(
            content="",
            provider=getattr(adapter, "name", "unknown"),
            model=request.model_name or getattr(adapter, "name", "unknown"),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            usage=None,
            finish_reason="error",
            safe_error=_safe_error(str(exc)),
            retryable=_is_retryable(str(exc)),
            parsed=None,
        )


def generate(
    request: LLMRequest,
    *,
    adapters: Mapping[str, LLMPort] | None = None,
) -> LLMResponse:
    """Execute a typed LLM request with retry/fallback. Output is never a transaction decision."""

    registry = dict(adapters or default_adapters())
    chain = _provider_chain(request.model_policy)
    last_error = "no_provider_attempted"
    last_provider = chain[0] if chain else "none"
    last_model = request.model_name or ""
    last_latency = 0.0
    primary_failed = False

    for index, provider_name in enumerate(chain):
        adapter = registry.get(provider_name)
        if adapter is None:
            last_error = f"adapter_missing:{provider_name}"
            continue
        attempts = 0
        max_attempts = max(0, int(request.max_retries)) + 1
        while attempts < max_attempts:
            attempts += 1
            result = _call_with_timeout(adapter, request)
            last_provider = result.provider or provider_name
            last_model = result.model
            last_latency = result.latency_ms
            if result.finish_reason == "timeout":
                last_error = result.safe_error or "provider_timeout"
                _metric(provider_name, "timeout")
                if attempts < max_attempts and result.retryable:
                    continue
                primary_failed = True
                break
            if result.safe_error or result.finish_reason == "error":
                last_error = result.safe_error or "provider_error"
                _metric(provider_name, "error")
                if result.retryable and attempts < max_attempts:
                    continue
                primary_failed = True
                break
            if request.expect_json:
                parsed = result.parsed if isinstance(result.parsed, dict) else _validate_json_content(result.content)
                if parsed is None:
                    last_error = "schema_validation_failed"
                    _metric(provider_name, "schema_failure")
                    primary_failed = True
                    # Schema failures are not retried on the same provider output; try fallback chain.
                    if index >= len(chain) - 1:
                        return LLMResponse(
                            content=result.content,
                            provider=result.provider,
                            model=result.model,
                            latency_ms=result.latency_ms,
                            usage=result.usage,
                            finish_reason="schema_failure",
                            safe_error=_safe_error(last_error),
                            parsed=None,
                            prompt_version=request.prompt_version,
                        )
                    break
                task_schema_error = _validate_task_schema(request.task, parsed)
                if task_schema_error:
                    last_error = task_schema_error
                    _metric(provider_name, "schema_failure")
                    primary_failed = True
                    if index >= len(chain) - 1:
                        return LLMResponse(
                            content=result.content,
                            provider=result.provider,
                            model=result.model,
                            latency_ms=result.latency_ms,
                            usage=result.usage,
                            finish_reason="schema_failure",
                            safe_error=_safe_error(last_error),
                            parsed=None,
                            prompt_version=request.prompt_version,
                        )
                    break
                finish = "fallback" if primary_failed or index > 0 else "stop"
                _metric(provider_name, finish)
                observability_service.increment_metric(
                    "llm_task_total",
                    status=f"{request.task}_{finish}"[:80],
                )
                return LLMResponse(
                    content=result.content or json.dumps(parsed, ensure_ascii=False),
                    provider=result.provider,
                    model=result.model,
                    latency_ms=result.latency_ms,
                    usage=result.usage,
                    finish_reason=finish,
                    safe_error="",
                    parsed=parsed,
                    prompt_version=request.prompt_version,
                )
            finish = "fallback" if primary_failed or index > 0 else "stop"
            _metric(provider_name, finish)
            return LLMResponse(
                content=result.content,
                provider=result.provider,
                model=result.model,
                latency_ms=result.latency_ms,
                usage=result.usage,
                finish_reason=finish,
                safe_error="",
                parsed=None,
                prompt_version=request.prompt_version,
            )
        # move to next provider in chain
        primary_failed = True

    _metric(last_provider, "error")
    return LLMResponse(
        content="",
        provider=last_provider,
        model=last_model,
        latency_ms=last_latency,
        usage=None,
        finish_reason="error" if "timeout" not in last_error else "timeout",
        safe_error=_safe_error(last_error),
        parsed=None,
        prompt_version=request.prompt_version,
    )
