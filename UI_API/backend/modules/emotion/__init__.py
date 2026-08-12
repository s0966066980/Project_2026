"""Emotion Diagnostics module.

Advisory only. Nothing here may block ordering or checkout, and the provider is
an adapter behind this surface rather than a service the rest of the
application knows about (ADR-0028, ADR-0029).
"""

from modules.emotion.application import (
    MODEL_PROFILE,
    analyze_event,
    analyze_live_diagnostic,
    capture_mode,
    clear_records,
    default_prompt,
    get_records,
    model_profiles,
    provider_status,
)

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
