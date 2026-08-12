import pytest
from pydantic import ValidationError

import config
from models.settings_contract import SettingsUpdateRequest

pytestmark = [pytest.mark.contract]


@pytest.mark.parametrize("mode", ["off", "periodic_ordering", "voice_only"])
def test_emotion_settings_use_only_the_three_canonical_modes(mode):
    update = SettingsUpdateRequest(
        EMOTION_CAPTURE_MODE=mode,
        EMOTION_MODEL_PROFILE="r1_omni",
        EMOTION_CLIP_SEC=5,
    )

    assert update.changed_settings()["EMOTION_CAPTURE_MODE"] == mode


@pytest.mark.parametrize("mode", ["voice", "periodic", "active", "shadow"])
def test_legacy_emotion_modes_are_rejected(mode):
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(EMOTION_CAPTURE_MODE=mode)


def test_emotion_enabled_is_not_a_second_mode_authority():
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(EMOTION_ENABLED=True)


@pytest.mark.parametrize(
    ("legacy_enabled", "legacy_mode", "expected"),
    [(True, "voice", "voice_only"), (True, "periodic", "periodic_ordering"), (False, "voice", "off")],
)
def test_legacy_settings_are_forward_migrated_once(legacy_enabled, legacy_mode, expected):
    settings = config._finalize_settings(
        {
            **config.DEFAULT_SETTINGS,
            "EMOTION_ENABLED": legacy_enabled,
            "EMOTION_CAPTURE_MODE": legacy_mode,
        }
    )
    assert settings["EMOTION_CAPTURE_MODE"] == expected
    assert "EMOTION_ENABLED" not in settings
