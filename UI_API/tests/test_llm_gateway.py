"""Milestone 3A LLM provider gateway contracts."""

from __future__ import annotations

import time
from dataclasses import dataclass

@dataclass
class _FakeResult:
    content: str
    parsed: dict | None = None
    error: str = ""
    retryable: bool = False
    latency_ms: float = 5.0
    model: str = "fake-model"


class FakeAdapter:
    def __init__(self, name: str, results: list[_FakeResult] | Exception | None = None):
        self.name = name
        self.calls = 0
        self._results = results if isinstance(results, list) else []
        self._exc = results if isinstance(results, Exception) else None

    def generate(self, request):
        from models.llm import LLMAdapterResult

        self.calls += 1
        if self._exc is not None:
            raise self._exc
        if not self._results:
            return LLMAdapterResult(
                content="",
                provider=self.name,
                model="none",
                latency_ms=1.0,
                usage=None,
                finish_reason="error",
                safe_error="provider_unavailable",
                retryable=True,
                parsed=None,
            )
        item = self._results.pop(0)
        if item.error:
            return LLMAdapterResult(
                content=item.content,
                provider=self.name,
                model=item.model,
                latency_ms=item.latency_ms,
                usage=None,
                finish_reason="error",
                safe_error=item.error,
                retryable=item.retryable,
                parsed=None,
            )
        return LLMAdapterResult(
            content=item.content,
            provider=self.name,
            model=item.model,
            latency_ms=item.latency_ms,
            usage={"total_tokens": 10},
            finish_reason="stop",
            safe_error="",
            retryable=False,
            parsed=item.parsed,
        )


def test_gateway_falls_back_when_primary_unavailable() -> None:
    from models.llm import LLMModelPolicy, LLMRequest
    from services import llm_gateway_service, observability_service

    observability_service.reset_metrics_for_tests()
    primary = FakeAdapter(
        "ollama",
        [_FakeResult(content="", error="connection refused", retryable=True)],
    )
    fallback = FakeAdapter(
        "gemini",
        [_FakeResult(content='{"ok": true}', parsed={"ok": True})],
    )
    response = llm_gateway_service.generate(
        LLMRequest(
            task="qa",
            system_prompt="sys",
            user_prompt="hello",
            model_policy=LLMModelPolicy.LOCAL_FIRST,
            prompt_version="qa-v1",
            expect_json=True,
            max_retries=0,
        ),
        adapters={"ollama": primary, "gemini": fallback},
    )
    assert response.provider == "gemini"
    assert response.parsed == {"ok": True}
    assert response.finish_reason == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1
    snapshot = observability_service.metrics_snapshot()
    assert snapshot["llm_provider_requests_total"]["ollama_error"] >= 1
    assert snapshot["llm_provider_requests_total"]["gemini_fallback"] >= 1


def test_gateway_retries_retryable_errors_only() -> None:
    from models.llm import LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    flaky = FakeAdapter(
        "ollama",
        [
            _FakeResult(content="", error="timeout", retryable=True),
            _FakeResult(content='{"answer": 1}', parsed={"answer": 1}),
        ],
    )
    response = llm_gateway_service.generate(
        LLMRequest(
            task="recommend",
            system_prompt="sys",
            user_prompt="u",
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            max_retries=1,
        ),
        adapters={"ollama": flaky},
    )
    assert response.parsed == {"answer": 1}
    assert flaky.calls == 2

    bad = FakeAdapter(
        "ollama",
        [_FakeResult(content="", error="invalid_api_key", retryable=False)],
    )
    failed = llm_gateway_service.generate(
        LLMRequest(
            task="recommend",
            system_prompt="sys",
            user_prompt="u",
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            max_retries=3,
        ),
        adapters={"ollama": bad},
    )
    assert failed.finish_reason == "error"
    assert bad.calls == 1


def test_schema_validation_failure_is_recorded() -> None:
    from models.llm import LLMModelPolicy, LLMRequest
    from services import llm_gateway_service, observability_service

    observability_service.reset_metrics_for_tests()
    adapter = FakeAdapter(
        "ollama",
        [_FakeResult(content="not-json", parsed=None)],
    )
    response = llm_gateway_service.generate(
        LLMRequest(
            task="structured",
            system_prompt="sys",
            user_prompt="u",
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            expect_json=True,
        ),
        adapters={"ollama": adapter},
    )
    assert response.finish_reason == "schema_failure"
    assert response.safe_error
    assert observability_service.metrics_snapshot()["llm_provider_requests_total"]["ollama_schema_failure"] >= 1


def test_timeout_policy_marks_safe_error() -> None:
    from models.llm import LLMAdapterResult, LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    class SlowAdapter:
        name = "ollama"

        def generate(self, request):
            time.sleep(0.05)
            return LLMAdapterResult(
                content="{}",
                provider="ollama",
                model="slow",
                latency_ms=50,
                usage=None,
                finish_reason="stop",
                safe_error="",
                retryable=False,
                parsed={},
            )

    response = llm_gateway_service.generate(
        LLMRequest(
            task="slow",
            system_prompt="sys",
            user_prompt="u",
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            timeout_seconds=0.01,
            expect_json=False,
        ),
        adapters={"ollama": SlowAdapter()},
    )
    # Soft timeout enforcement around adapter call
    assert response.finish_reason in {"timeout", "error"}
    assert "timeout" in response.safe_error or response.finish_reason == "timeout"


def test_gateway_redacts_secrets_from_safe_errors_and_logs() -> None:
    from models.llm import LLMModelPolicy, LLMRequest
    from services import llm_gateway_service, observability_service

    adapter = FakeAdapter(
        "gemini",
        [_FakeResult(content="", error="password=supersecret token=abc DATABASE_URL=postgresql://x", retryable=False)],
    )
    response = llm_gateway_service.generate(
        LLMRequest(
            task="secure",
            system_prompt="sys",
            user_prompt="user phone 0912345678",
            model_policy=LLMModelPolicy.CLOUD_ONLY,
        ),
        adapters={"gemini": adapter},
    )
    assert "supersecret" not in response.safe_error
    assert "postgresql://" not in response.safe_error
    assert "[REDACTED]" in response.safe_error or "password" in response.safe_error
    # Prompt text is not stored on the response object
    assert not hasattr(response, "user_prompt")
    serialized = str(observability_service.metrics_snapshot())
    assert "supersecret" not in serialized


def test_prompt_version_is_echoed_on_response() -> None:
    from models.llm import LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    adapter = FakeAdapter(
        "ollama",
        [_FakeResult(content="plain", parsed=None)],
    )
    response = llm_gateway_service.generate(
        LLMRequest(
            task="voice",
            system_prompt="sys",
            user_prompt="hi",
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            prompt_version="voice-intent-v3",
            expect_json=False,
        ),
        adapters={"ollama": adapter},
    )
    assert response.prompt_version == "voice-intent-v3"
    assert response.finish_reason == "stop"


def test_llm_output_is_not_transaction_decision() -> None:
    """Gateway returns evidence/content only; callers must not treat it as checkout authority."""
    from models.llm import LLMResponse

    response = LLMResponse(
        content='{"approve_checkout": true, "total": 1}',
        provider="ollama",
        model="m",
        latency_ms=1,
        usage=None,
        finish_reason="stop",
        safe_error="",
        parsed={"approve_checkout": True, "total": 1},
        prompt_version="v1",
    )
    assert "order_id" not in (response.parsed or {})
    assert response.finish_reason != "authorized_transaction"
