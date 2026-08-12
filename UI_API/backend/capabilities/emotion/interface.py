"""Published advisory-only Emotion Diagnostics surface."""

from __future__ import annotations

from typing import Any

from capabilities.emotion.contracts import EmotionCapabilityError, EmotionObservation
from modules.emotion import application as _emotion
from modules.emotion.application import (
    MODEL_PROFILE,
    analyze_event,
    analyze_live_diagnostic,
    default_prompt,
    model_profiles,
)

# The implementation used to sit in services/ and be reached by a call-time
# import inside every function here, which is what kept this capability on the
# frozen legacy-layer list. It now lives in modules/emotion.


def default_profile() -> str:
    return str(MODEL_PROFILE)


def readiness() -> dict[str, Any]:
    """Read the provider state at call time, not at import time.

    Binding `model_profiles` here would freeze the answer to whatever the
    provider looked like when the process started, which is the opposite of
    what a readiness probe is for.
    """

    profile = (_emotion.model_profiles() or [{}])[0]
    ready = bool(profile.get("ready"))
    return {"status": "ready" if ready else "unavailable", "ready": ready, "provider": profile}


def list_records(limit: int = 200) -> list[dict[str, Any]]:
    return _emotion.get_records(limit)


def clear_records() -> int:
    return _emotion.clear_records()


__all__ = [
    "EmotionCapabilityError",
    "EmotionObservation",
    "analyze_event",
    "analyze_live_diagnostic",
    "clear_records",
    "default_profile",
    "default_prompt",
    "list_records",
    "model_profiles",
    "readiness",
]
