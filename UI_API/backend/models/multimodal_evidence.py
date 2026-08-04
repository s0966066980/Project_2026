"""Evidence contracts for emotion / multimodal providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class MultimodalEvidenceRequest:
    media_path: str
    question: str
    media_mode: str = "video_audio"  # video_audio | audio_only
    session_ref: str = ""
    event_type: str = ""
    speech_text: str = ""
    timeout_seconds: float = 20.0
    max_retries: int = 0
    skip_quality_check: bool = False
    prompt_version: str = "multimodal-v1"
    # Scope-safe metadata only (no PII / raw media paths in logs)
    scope_safe_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MultimodalEvidence:
    provider: str
    model_version: str
    timestamp: str
    confidence: float | None
    signals: dict[str, Any]
    quality: str
    latency_ms: float
    safe_metadata: dict[str, Any] = field(default_factory=dict)
    safe_error: str = ""
    has_evidence: bool = False
    status: str = "ok"  # ok | no_evidence | skipped | error | disabled


class MultimodalEvidencePort(Protocol):
    name: str

    def analyze(self, request: MultimodalEvidenceRequest) -> MultimodalEvidence: ...
