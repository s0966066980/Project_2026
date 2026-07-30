"""The store's configured routing must actually decide which provider answers."""

from __future__ import annotations

import pytest

import config
from models.llm import LLMAdapterResult, LLMModelPolicy, LLMRequest
from services import llm_gateway_service, llm_routing_service


class RecordingAdapter:
    def __init__(self, name: str, *, fails: bool = False):
        self.name = name
        self.fails = fails
        self.calls: list[str] = []

    def generate(self, request: LLMRequest) -> LLMAdapterResult:
        self.calls.append(request.model_name)
        if self.fails:
            return LLMAdapterResult(
                content="", provider=self.name, model=request.model_name, latency_ms=1.0,
                usage=None, finish_reason="error", safe_error="provider_unavailable",
                retryable=True, parsed=None,
            )
        return LLMAdapterResult(
            content='{"ok": true}', provider=self.name, model=request.model_name, latency_ms=1.0,
            usage=None, finish_reason="stop", safe_error="", retryable=False, parsed={"ok": True},
        )


@pytest.fixture
def settings(monkeypatch):
    values: dict = {}
    monkeypatch.setattr(config, "get", lambda key, default=None: values.get(key, default))
    return values


def _request() -> LLMRequest:
    return LLMRequest(
        task="ai_push_copy",
        system_prompt="s",
        user_prompt="u",
        model_policy=llm_routing_service.configured_policy(),
        expect_json=False,
        model_name="qwen3.5:4b",
        max_retries=0,
    )


def test_cloud_only_policy_never_reaches_the_local_provider(settings):
    settings.update({"LLM_ROUTING_POLICY": "cloud_only", "NIM_MODEL_NAME": "meta/llama-3.1-70b-instruct"})
    ollama, nim = RecordingAdapter("ollama"), RecordingAdapter("nvidia_nim")

    response = llm_gateway_service.generate(_request(), adapters={"ollama": ollama, "nvidia_nim": nim})

    assert response.provider == "nvidia_nim"
    assert ollama.calls == []
    assert nim.calls == ["meta/llama-3.1-70b-instruct"]


def test_local_only_policy_never_reaches_the_cloud_provider(settings):
    settings.update({"LLM_ROUTING_POLICY": "local_only"})
    ollama, nim = RecordingAdapter("ollama"), RecordingAdapter("nvidia_nim")

    response = llm_gateway_service.generate(_request(), adapters={"ollama": ollama, "nvidia_nim": nim})

    assert response.provider == "ollama"
    assert nim.calls == []


def test_cloud_first_falls_back_to_local_when_the_cloud_fails(settings):
    settings.update({"LLM_ROUTING_POLICY": "cloud_first", "NIM_MODEL_NAME": "meta/llama-3.1-8b-instruct"})
    ollama = RecordingAdapter("ollama")
    nim = RecordingAdapter("nvidia_nim", fails=True)

    response = llm_gateway_service.generate(_request(), adapters={"ollama": ollama, "nvidia_nim": nim})

    assert response.provider == "ollama"
    assert nim.calls == ["meta/llama-3.1-8b-instruct"]
    assert ollama.calls == ["qwen3.5:4b"]


def test_nvidia_nim_is_the_only_cloud_provider_in_the_chain(settings):
    settings.update({"LLM_ROUTING_POLICY": "cloud_only"})
    assert llm_gateway_service._provider_chain(llm_routing_service.configured_policy()) == ["nvidia_nim"]
    assert "nvidia_nim" in llm_gateway_service.default_adapters()
    assert "gemini" not in llm_gateway_service.default_adapters()
    assert "openai" not in llm_gateway_service.default_adapters()


def test_voice_tasks_use_the_configured_cloud_voice_model(settings):
    settings.update({"LLM_ROUTING_POLICY": "cloud_only",
                     "NIM_MODEL_NAME": "meta/llama-3.1-70b-instruct",
                     "NIM_VOICE_MODEL": "meta/llama-3.1-8b-instruct"})
    nim = RecordingAdapter("nvidia_nim")

    llm_gateway_service.generate(
        LLMRequest(task="voice_assist", system_prompt="s", user_prompt="u",
                   model_policy=LLMModelPolicy.CLOUD_ONLY, expect_json=False,
                   model_name="qwen3.5:4b", max_retries=0),
        adapters={"nvidia_nim": nim},
    )

    assert nim.calls == ["meta/llama-3.1-8b-instruct"]


def test_readiness_marks_a_policy_degraded_only_when_a_used_half_cannot_serve(settings, monkeypatch):
    settings.update({"LLM_ROUTING_POLICY": "local_only"})
    monkeypatch.setattr(llm_routing_service, "_ollama_reachable", lambda timeout=2.0: (True, ""))
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")

    local_only = llm_routing_service.readiness()
    assert local_only["degraded"] is False

    settings["LLM_ROUTING_POLICY"] = "cloud_first"
    cloud_first = llm_routing_service.readiness()
    assert cloud_first["degraded"] is True
    assert cloud_first["blocking"] == ["cloud"]


def test_legacy_ai_provider_migrates_to_a_policy_and_drops_credentials():
    migrated = config.migrate_llm_routing_settings({
        "AI_PROVIDER": "openai",
        "QA_AI_PROVIDER": "openai",
        "ENABLE_GEMINI_OPTIONS": False,
        "STT_API_KEY": "sk-should-not-persist",
        "MODEL_NAME": "qwen3.5:4b",
    })

    assert migrated["LLM_ROUTING_POLICY"] == "cloud_first"
    assert migrated["MODEL_NAME"] == "qwen3.5:4b"
    assert "AI_PROVIDER" not in migrated
    assert "ENABLE_GEMINI_OPTIONS" not in migrated
    assert "STT_API_KEY" not in migrated


def test_legacy_llm_cloud_provider_selection_is_dropped_and_still_migrates_to_cloud_first():
    migrated = config.migrate_llm_routing_settings({
        "LLM_CLOUD_PROVIDER": "gemini",
        "GEMINI_MODEL_NAME": "gemini-3-flash-preview",
    })

    assert migrated["LLM_ROUTING_POLICY"] == "cloud_first"
    assert "LLM_CLOUD_PROVIDER" not in migrated
    # Stale provider-specific model keys are harmless leftovers; NIM_MODEL_NAME governs now.
    assert "GEMINI_MODEL_NAME" in migrated
