"""LLM Gateway: timeout, retry, fallback, metrics, and prompt-version contract."""

from __future__ import annotations

import concurrent.futures
import json
import time
from dataclasses import replace
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
# Traditional Chinese rendering of the safe_error codes adapters emit. Shared by every Admin
# surface that shows a provider failure — connectivity tests and the diagnostic prompt tool —
# so the same failure never reads differently depending on which surface reported it.
SAFE_ERROR_MESSAGES: dict[str, str] = {
    "missing_credential": "缺少 API 金鑰，未送出請求。",
    "provider_timeout": "請求逾時。",
    "invalid_provider_payload": "回應格式無法解析。",
    "response_truncated": "回應在寫完前就達到長度上限。推理型模型的思考過程也會佔用額度，請改用非推理型模型。",
}


def describe_safe_error(code: str) -> str:
    """Render a safe_error code for an operator. Unknown codes pass through unchanged."""

    return SAFE_ERROR_MESSAGES.get(code, code)


TASK_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    # Authored in Admin, not generated per request — the gateway only sees this task when an
    # operator presses 產生推薦詞, never on a Kiosk push.
    "ai_push_copy": frozenset({"push_text"}),
    "voice_assist": frozenset({"ai_response"}),
    "payment_assist": frozenset(),  # free-form assist message fields accepted
    "emotion_extract": frozenset({"emotion", "intensity"}),
}


def _provider_chain(policy: LLMModelPolicy) -> list[str]:
    from services import llm_routing_service

    cloud = llm_routing_service.CLOUD_PROVIDER
    if policy is LLMModelPolicy.LOCAL_ONLY:
        return ["ollama"]
    if policy is LLMModelPolicy.CLOUD_ONLY:
        return [cloud]
    if policy is LLMModelPolicy.CLOUD_FIRST:
        return [cloud, "ollama"]
    return ["ollama", cloud]


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


class NvidiaNimAdapter:
    """NVIDIA NIM: the sole cloud text provider, spoken via the OpenAI chat-completions schema."""

    name = "nvidia_nim"

    def generate(self, request: LLMRequest) -> LLMAdapterResult:
        import requests

        import ai_services
        import config

        model = request.model_name or "meta/llama-3.1-8b-instruct"
        started = time.perf_counter()
        api_key = config.NVIDIA_API_KEY
        if not api_key:
            return LLMAdapterResult(
                content="",
                provider=self.name,
                model=model,
                latency_ms=0.0,
                usage=None,
                finish_reason="error",
                safe_error="missing_credential",
                retryable=False,
                parsed=None,
            )
        base_url = str(config.NVIDIA_API_BASE_URL or "https://integrate.api.nvidia.com/v1").rstrip("/")
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        if request.max_tokens:
            payload["max_tokens"] = int(request.max_tokens)
        if request.expect_json:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                timeout=max(1.0, float(request.timeout_seconds)),
            )
            response.raise_for_status()
            body = response.json()
            choice = body["choices"][0]
            content = str(choice["message"]["content"] or "")
            provider_finish = str(choice.get("finish_reason") or "")
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
        except Exception as exc:  # noqa: BLE001 - provider text is normalised before it leaves here
            provider_error = str(exc)
            return LLMAdapterResult(
                content="",
                provider=self.name,
                model=model,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                usage=None,
                finish_reason="error",
                safe_error=_safe_error(provider_error),
                retryable=_is_retryable(provider_error),
                parsed=None,
            )
        latency_ms = (time.perf_counter() - started) * 1000.0
        # Reasoning models spend the same max_tokens budget on their hidden thinking, so a small
        # budget yields finish_reason='length' with empty content. That is a truncation, not a
        # malformed payload — conflating the two sends operators hunting for a parsing bug.
        if provider_finish == "length" and not content.strip():
            return LLMAdapterResult(
                content="",
                provider=self.name,
                model=model,
                latency_ms=latency_ms,
                usage=usage,
                finish_reason="error",
                safe_error="response_truncated",
                retryable=False,
                parsed=None,
            )
        parsed = None
        if request.expect_json:
            parsed = ai_services.parse_llm_json(content, request.response_tag)
            if not isinstance(parsed, dict) or "error" in parsed:
                parsed = _validate_json_content(content)
            if parsed is None:
                return LLMAdapterResult(
                    content=content,
                    provider=self.name,
                    model=model,
                    latency_ms=latency_ms,
                    usage=usage,
                    finish_reason="error",
                    # A partial JSON body is still truncation rather than a provider defect.
                    safe_error="response_truncated" if provider_finish == "length" else "invalid_provider_payload",
                    retryable=provider_finish != "length",
                    parsed=None,
                )
        return LLMAdapterResult(
            content=content,
            provider=self.name,
            model=model,
            latency_ms=latency_ms,
            usage=usage,
            finish_reason="stop",
            safe_error="",
            retryable=False,
            parsed=parsed,
            # JSON repair can turn a value cut off mid-string into a syntactically valid but
            # empty field (e.g. {"push_text": ""}), which parses successfully yet is missing
            # the content a task schema check requires — that failure needs to read as
            # truncation, not as "the model omitted this field".
            provider_truncated=provider_finish == "length",
        )


def default_adapters() -> dict[str, LLMPort]:
    return {"ollama": OllamaAdapter(), "nvidia_nim": NvidiaNimAdapter()}


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
    """Stream tokens from Ollama; a cloud-only store gets one non-streamed chunk instead.

    Only the local adapter streams. Rather than quietly using Ollama when the store asked for
    cloud-only, fall back to a normal generate call and emit its text as a single token.
    """

    import ai_services
    from services import llm_routing_service

    if not llm_routing_service.allows_local(request.model_policy):
        response = generate(request)
        if response.content:
            yield response.content
        return

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


def _request_for_provider(request: LLMRequest, provider_name: str) -> LLMRequest:
    """Callers name a local model; a cloud provider in the chain needs its own configured model."""

    if provider_name == "ollama":
        return request
    from services import llm_routing_service

    model = llm_routing_service.cloud_model(voice=str(request.task) == "voice_assist")
    return replace(request, model_name=model) if model else request


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
        attempt_request = _request_for_provider(request, provider_name)
        attempts = 0
        max_attempts = max(0, int(request.max_retries)) + 1
        while attempts < max_attempts:
            attempts += 1
            result = _call_with_timeout(adapter, attempt_request)
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
                    # A required field parsed as empty because the provider cut the response
                    # off mid-value, not because it chose to omit the field.
                    last_error = "response_truncated" if result.provider_truncated else task_schema_error
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
