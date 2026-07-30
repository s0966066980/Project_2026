"""Emotion Runtime Profile must override stale persisted UI settings."""

from __future__ import annotations


def test_process_emotion_enablement_overrides_persisted_setting(monkeypatch) -> None:
    import config
    from backend.services import emotion_service

    monkeypatch.setattr(
        config,
        "load_settings",
        lambda: {"EMOTION_LLAMA_ENABLED": False},
    )
    monkeypatch.setenv("EMOTION_LLAMA_ENABLED", "true")

    assert config.get("EMOTION_LLAMA_ENABLED", False) is True
    assert emotion_service.is_enabled() is True


def test_process_emotion_disablement_overrides_persisted_setting(monkeypatch) -> None:
    import config
    from backend.services import emotion_service

    monkeypatch.setattr(
        config,
        "load_settings",
        lambda: {"EMOTION_LLAMA_ENABLED": True},
    )
    monkeypatch.setenv("EMOTION_LLAMA_ENABLED", "false")

    assert config.get("EMOTION_LLAMA_ENABLED", True) is False
    assert emotion_service.is_enabled() is False
