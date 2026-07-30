"""Typed contracts for the LLM provider gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class LLMModelPolicy(str, Enum):
    LOCAL_FIRST = "local_first"
    CLOUD_FIRST = "cloud_first"
    LOCAL_ONLY = "local_only"
    CLOUD_ONLY = "cloud_only"


@dataclass(frozen=True)
class LLMRequest:
    task: str
    system_prompt: str
    user_prompt: str
    model_policy: LLMModelPolicy = LLMModelPolicy.LOCAL_FIRST
    timeout_seconds: float = 30.0
    prompt_version: str = "v1"
    expect_json: bool = True
    response_tag: str = ""
    model_name: str = ""
    max_tokens: int | None = None
    max_retries: int = 1
    scope_safe_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    content: str
    provider: str
    model: str
    latency_ms: float
    usage: dict[str, float] | None
    finish_reason: str
    safe_error: str
    parsed: dict[str, Any] | None = None
    prompt_version: str = "v1"


@dataclass(frozen=True)
class LLMAdapterResult:
    content: str
    provider: str
    model: str
    latency_ms: float
    usage: dict[str, float] | None
    finish_reason: str
    safe_error: str
    retryable: bool
    parsed: dict[str, Any] | None = None
    # True when the provider itself reported finish_reason='length' even though JSON repair
    # produced a syntactically valid (but semantically incomplete) result — e.g. a cut-off value
    # got repaired into an empty string. Lets a later schema failure be reported as truncation
    # rather than a misleading "the model didn't include this field" message.
    provider_truncated: bool = False


class LLMPort(Protocol):
    name: str

    def generate(self, request: LLMRequest) -> LLMAdapterResult: ...
