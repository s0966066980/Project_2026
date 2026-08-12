from pathlib import Path

import pytest

pytestmark = [pytest.mark.architecture]
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_passive_keyword_recorder_is_not_a_supported_project_surface() -> None:
    assert not (REPOSITORY_ROOT / "tools" / "demo_passive_voice.py").exists()

    tools_readme = (REPOSITORY_ROOT / "tools" / "README.md").read_text(encoding="utf-8")
    assert "demo_passive_voice.py" not in tools_readme
    assert "PASSIVE_VOICE_" not in tools_readme
