import pytest
from pydantic import ValidationError

import config
from models.settings_contract import SettingsUpdateRequest


def test_emotion_settings_are_generic_and_r1_runtime_is_not_selectable():
    update = SettingsUpdateRequest(EMOTION_ENABLED=True, EMOTION_ANALYSIS_MODE="paired")
    assert update.changed_settings() == {"EMOTION_ENABLED": True, "EMOTION_ANALYSIS_MODE": "paired"}
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(EMOTION_PROVIDER="r1_omni")
    assert "EMOTION_PROVIDER" not in config.DEFAULT_SETTINGS
    assert config.DEFAULT_SETTINGS["EMOTION_PROMPT"]

