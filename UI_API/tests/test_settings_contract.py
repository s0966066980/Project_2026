import pytest
from pydantic import ValidationError

import config
from models.settings_contract import SettingsUpdateRequest


def test_emotion_settings_expose_only_the_single_pass_contract():
    update = SettingsUpdateRequest(
        EMOTION_MODEL_PROFILE="r1_omni",
        EMOTION_CAPTURE_MODE="periodic_ordering",
        EMOTION_CLIP_SEC=30,
    )
    assert update.changed_settings() == {
        "EMOTION_MODEL_PROFILE": "r1_omni",
        "EMOTION_CAPTURE_MODE": "periodic_ordering",
        "EMOTION_CLIP_SEC": 30,
    }
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(EMOTION_PROVIDER="r1_omni")
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(EMOTION_ANALYSIS_MODE="paired")
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(EMOTION_CLIP_SEC=31)
    assert "EMOTION_PROVIDER" not in config.DEFAULT_SETTINGS
    assert "EMOTION_ANALYSIS_MODE" not in config.DEFAULT_SETTINGS
    assert config.DEFAULT_SETTINGS["EMOTION_PROMPT"]


def test_ai_runtime_settings_can_be_overridden_by_container_environment(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "qwen2.5:0.5b")
    monkeypatch.setenv("STT_PROVIDER", "faster_whisper")
    monkeypatch.setenv("STT_MODEL", "tiny")
    monkeypatch.setenv("TTS_PROVIDER", "edge")
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("VOICE_LLM_PREWARM_ENABLED", "false")

    settings = config._finalize_settings(config.DEFAULT_SETTINGS.copy())

    assert settings["MODEL_NAME"] == "qwen2.5:0.5b"
    assert settings["STT_PROVIDER"] == "faster_whisper"
    assert settings["STT_MODEL"] == "tiny"
    assert settings["TTS_PROVIDER"] == "edge"
    assert settings["RAG_ENABLED"] is True
    assert settings["VOICE_LLM_PREWARM_ENABLED"] is False
