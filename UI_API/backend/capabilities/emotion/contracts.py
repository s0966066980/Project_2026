"""Published advisory-only Emotion Diagnostics vocabulary."""

from __future__ import annotations

from typing import TypedDict


class EmotionObservation(TypedDict, total=False):
    status: str
    mode: str
    model_profile: str
    emotion: str
    confidence: float
    evidence_ref: str


class EmotionCapabilityError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
