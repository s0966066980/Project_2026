"""Milestone 5C: production LLM callers route through the gateway."""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
SERVICES = BACKEND / "services"

# Production application services must not import ai_services directly.
# Allowed: llm_gateway adapters, test_service (test routes), bootstrap warm-up.
_FORBIDDEN_DIRECT_AI_IMPORT = frozenset(
    {
        "ai_push_service.py",
        "voice_service.py",
        "emotion_service.py",
        "recommendation_service.py",
        "recommendation_engine_service.py",
        "rag_document_service.py",
        "rag_governance_service.py",
        "checkout_service.py",
        "worker_handlers.py",
    }
)


import pytest


@pytest.mark.security
@pytest.mark.core
def test_production_services_do_not_import_ai_services_directly() -> None:
    offenders: list[str] = []
    for name in sorted(_FORBIDDEN_DIRECT_AI_IMPORT):
        path = SERVICES / name
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "ai_services" or alias.name.startswith("ai_services."):
                        offenders.append(name)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "ai_services" or (node.module or "").startswith("ai_services."):
                    offenders.append(name)
    assert offenders == [], f"direct ai_services import in production services: {offenders}"


def test_only_gateway_adapters_import_ai_services_for_generation() -> None:
    gateway = (SERVICES / "llm_gateway_service.py").read_text(encoding="utf-8")
    assert "import ai_services" in gateway
    assert "class OllamaAdapter" in gateway
    assert "class GeminiAdapter" in gateway


def test_timeout_returns_within_budget_without_waiting_for_thread() -> None:
    from models.llm import LLMAdapterResult, LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    class SlowAdapter:
        name = "ollama"

        def generate(self, request):
            time.sleep(0.4)
            return LLMAdapterResult(
                content="{}",
                provider="ollama",
                model="slow",
                latency_ms=400,
                usage=None,
                finish_reason="stop",
                safe_error="",
                retryable=False,
                parsed={},
            )

    started = time.perf_counter()
    response = llm_gateway_service.generate(
        LLMRequest(
            task="slow",
            system_prompt="sys",
            user_prompt="u",
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            timeout_seconds=0.05,
            expect_json=False,
            max_retries=0,
        ),
        adapters={"ollama": SlowAdapter()},
    )
    elapsed = time.perf_counter() - started
    assert response.finish_reason == "timeout"
    # Must return near the timeout budget; must not wait for the 0.4s sleep via pool shutdown.
    assert elapsed < 0.25


def test_ai_push_task_schema_requires_recommendation_and_text() -> None:
    from models.llm import LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    class IncompleteAdapter:
        name = "ollama"

        def generate(self, request):
            from models.llm import LLMAdapterResult

            return LLMAdapterResult(
                content='{"push_text":"only text"}',
                provider="ollama",
                model="m",
                latency_ms=1,
                usage=None,
                finish_reason="stop",
                safe_error="",
                retryable=False,
                parsed={"push_text": "only text"},
            )

    response = llm_gateway_service.generate(
        LLMRequest(
            task="ai_push_copy",
            system_prompt="s",
            user_prompt="u",
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            expect_json=True,
            max_retries=0,
        ),
        adapters={"ollama": IncompleteAdapter()},
    )
    assert response.finish_reason == "schema_failure"


def test_ai_push_uses_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from models.llm import LLMResponse
    from services import ai_push_service

    calls: list[str] = []

    def fake_generate(request, **kwargs):
        calls.append(request.task)
        return LLMResponse(
            content='{"recommendation_id":"MCD001","push_text":"大麥克套餐現在很適合來一份搭配點餐剛剛好"}',
            provider="ollama",
            model="m",
            latency_ms=1,
            usage=None,
            finish_reason="stop",
            safe_error="",
            parsed={
                "recommendation_id": "MCD001",
                "push_text": "大麥克套餐現在很適合來一份搭配點餐剛剛好",
            },
            prompt_version=request.prompt_version,
        )

    monkeypatch.setattr(ai_push_service.llm_gateway_service, "generate", fake_generate)
    monkeypatch.setattr(
        ai_push_service.config,
        "get",
        lambda key, default=None: {
            "AI_PUSH_SYSTEM_PROMPT": "system",
            "AI_PUSH_TEXT_MIN": 18,
            "AI_PUSH_TEXT_MAX": 34,
            "OLLAMA_NUM_PREDICT": 220,
            "MODEL_NAME": "model",
            "OLLAMA_TIMEOUT": 5,
        }.get(key, default),
    )

    class _Sem:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    text, status = asyncio.run(
        ai_push_service._generate_push_text(
            {"audience": "guest", "rag": {"context": "", "offers": []}, "menu_items": []},
            "MCD001",
            "大麥克套餐",
            _Sem(),
        )
    )
    assert calls == ["ai_push_copy"]
    assert status == "success"
    assert "大麥克" in text
