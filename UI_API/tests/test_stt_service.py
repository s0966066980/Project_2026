from __future__ import annotations

import sys
from types import SimpleNamespace


def test_faster_whisper_runtime_uses_ctranslate2_without_torch(monkeypatch) -> None:
    from services import stt_service

    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 0))
    monkeypatch.delitem(sys.modules, "torch", raising=False)

    assert stt_service._faster_whisper_runtime() == ("cpu", "int8")


def test_faster_whisper_runtime_selects_cuda_when_available(monkeypatch) -> None:
    from services import stt_service

    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))

    assert stt_service._faster_whisper_runtime() == ("cuda", "float16")
