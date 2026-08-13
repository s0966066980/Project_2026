"""The local provider has to respect the bound its caller declared.

A caller states `timeout_seconds` because it knows what its own consumer will
wait for: the Admin connectivity probe allows 15s, the Admin diagnostic 60s.
The NVIDIA adapter passed that straight to `requests`; the Ollama adapter
discarded it and always used `OLLAMA_TIMEOUT` (120s by default).

The visible result was an Admin LLM test that "failed" for no stated reason:
the browser gave up at its own 15s client bound while the server kept
generating, then finished two minutes later and returned HTTP 200 to nobody.
"""

import pytest

import ai_services
from models.llm import LLMRequest
from services import llm_gateway_service

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.fixture
def recorded_timeouts(monkeypatch):
    """Capture the timeout the HTTP layer is actually handed."""

    seen: list[float] = []

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"response": '{"ok": true}'}

    class _Session:
        def post(self, url, json=None, timeout=None, **kwargs):
            seen.append(timeout)
            return _Response()

    monkeypatch.setattr(ai_services, "_get_ollama_session", lambda: _Session())
    return seen


def _request(**overrides) -> LLMRequest:
    values = {
        "task": "connectivity_probe",
        "system_prompt": "system",
        "user_prompt": "ping",
        "prompt_version": "v1",
        "timeout_seconds": 15.0,
        "expect_json": True,
        "model_name": "qwen3.5:4b",
        "max_tokens": 16,
        "max_retries": 0,
    }
    values.update(overrides)
    return LLMRequest(**values)


def test_the_json_path_waits_only_as_long_as_the_caller_allowed(recorded_timeouts):
    llm_gateway_service.OllamaAdapter().generate(_request(timeout_seconds=15.0))

    assert recorded_timeouts == [15.0], "the local adapter ignored the caller's bound"


def test_the_free_text_path_waits_only_as_long_as_the_caller_allowed(recorded_timeouts):
    llm_gateway_service.OllamaAdapter().generate(_request(expect_json=False, timeout_seconds=60.0))

    assert recorded_timeouts == [60.0]


def test_a_caller_that_states_no_bound_gets_the_deployment_default(monkeypatch, recorded_timeouts):
    """Absent a stated bound, the deployment's own setting still applies."""

    monkeypatch.setattr(ai_services.config, "get", lambda key, default=None: 30 if key == "OLLAMA_TIMEOUT" else default)

    ai_services.ask_ollama("system", "ping", "tag", "qwen3.5:4b")

    assert recorded_timeouts == [30.0]


def test_a_nonsensical_bound_does_not_become_an_instant_failure(recorded_timeouts):
    """Zero would abort before the request left the process; one second is the floor."""

    llm_gateway_service.OllamaAdapter().generate(_request(timeout_seconds=0))

    assert recorded_timeouts == [1.0]
