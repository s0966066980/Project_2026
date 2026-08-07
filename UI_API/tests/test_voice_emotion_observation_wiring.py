"""The Voice Turn runtime reaches emotion observation through a lazy import.

`modules/voice_turn/runtime.py` imports from `services.voice_service` inside a
function, so nothing at import time — and no other test — proves the target still
exists. A rename, or a cleanup that trims one function too many, would surface
only when a customer finishes a Voice Turn. This pins the seam.
"""

import inspect
import re

from modules.voice_turn import runtime

import services.voice_service as voice_service


def test_voice_turn_runtime_lazy_imports_resolve():
    imported = re.findall(r"from services\.voice_service import ([\w, ]+)", inspect.getsource(runtime))
    assert imported, "voice_turn runtime no longer imports from services.voice_service"
    for group in imported:
        for name in (part.strip() for part in group.split(",")):
            assert hasattr(voice_service, name), f"services.voice_service is missing {name}"


def test_voice_service_only_serves_emotion_observation():
    """The customer-facing voice pipeline lives in modules.voice_turn (ADR-0023).

    Keeping a second voice implementation here is what let contradictory playback
    semantics survive alongside the durable module, so the module stays trimmed.
    """
    public = [name for name in vars(voice_service) if name.startswith("handle_")]
    assert public == [], f"unexpected voice handlers left in voice_service: {public}"
