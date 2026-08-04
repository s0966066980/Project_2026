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
    assert "class NvidiaNimAdapter" in gateway


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


def test_ai_push_task_schema_requires_push_text() -> None:
    """Authoring only needs the sentence; the item is already known from the request path."""

    from models.llm import LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    class NoTextAdapter:
        name = "ollama"

        def generate(self, request):
            from models.llm import LLMAdapterResult

            return LLMAdapterResult(
                content='{"recommendation_id":"MCD001"}',
                provider="ollama",
                model="m",
                latency_ms=1,
                usage=None,
                finish_reason="stop",
                safe_error="",
                retryable=False,
                parsed={"recommendation_id": "MCD001"},
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
        adapters={"ollama": NoTextAdapter()},
    )
    assert response.finish_reason == "schema_failure"


def test_schema_failure_from_a_truncated_response_reports_truncation() -> None:
    """JSON repair can turn a value cut off mid-string into a syntactically valid but empty
    field (e.g. {"push_text": ""}). The schema check correctly calls that missing, but the
    real cause is the provider running out of budget — the error code must say so, or an
    operator ends up debugging a "field omitted" bug that doesn't exist."""

    from models.llm import LLMAdapterResult, LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    class TruncatedAdapter:
        name = "ollama"

        def generate(self, request):
            return LLMAdapterResult(
                content='{"push_text": ""}',
                provider="ollama",
                model="m",
                latency_ms=1,
                usage=None,
                finish_reason="stop",
                safe_error="",
                retryable=False,
                parsed={"push_text": ""},
                provider_truncated=True,
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
        adapters={"ollama": TruncatedAdapter()},
    )
    assert response.finish_reason == "schema_failure"
    assert response.safe_error == "response_truncated"


def test_schema_failure_without_truncation_keeps_the_original_code() -> None:
    """A model that simply never produced the field is a different problem from a truncated
    one, so the two must stay distinguishable."""

    from models.llm import LLMAdapterResult, LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    class MissingFieldAdapter:
        name = "ollama"

        def generate(self, request):
            return LLMAdapterResult(
                content='{"push_text": ""}',
                provider="ollama",
                model="m",
                latency_ms=1,
                usage=None,
                finish_reason="stop",
                safe_error="",
                retryable=False,
                parsed={"push_text": ""},
                provider_truncated=False,
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
        adapters={"ollama": MissingFieldAdapter()},
    )
    assert response.finish_reason == "schema_failure"
    assert response.safe_error == "schema_missing_fields"


def test_ai_push_service_never_reaches_an_llm() -> None:
    """Kiosk push copy is authored ahead of time, so serving it must not import a model path.

    This is the guard on ADR-0016: if someone reintroduces runtime generation, a push can once
    again be slow, fail, or assert a promotion the store is not running.
    """

    source = (SERVICES / "ai_push_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
            if node.module:
                imported.add(node.module.split(".")[0])

    assert "llm_gateway_service" not in imported
    assert "ai_services" not in imported
    assert "LLMRequest" not in imported

