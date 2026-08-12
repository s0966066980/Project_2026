"""Public Application API for the Emotion Diagnostics module."""

from __future__ import annotations

from modules.emotion import _emotion_service
from modules.emotion._emotion_service import (
    MODEL_PROFILE,
    analyze_event,
    analyze_live_diagnostic,
    capture_mode,
    default_prompt,
)
from modules.emotion.adapters.emotion_log import clear_records, get_records
from modules.emotion.adapters.r1_omni import configured_provider_status as provider_status


def model_profiles():
    """Ask the provider now.

    Re-exporting the function object would bind whatever was defined at import
    time. Readiness has to reflect the provider as it is when asked, and a
    frozen answer is the failure this capability exists to avoid.
    """

    return _emotion_service.model_profiles()


__all__ = [
    "MODEL_PROFILE",
    "analyze_event",
    "analyze_live_diagnostic",
    "capture_mode",
    "clear_records",
    "default_prompt",
    "get_records",
    "model_profiles",
    "provider_status",
]
