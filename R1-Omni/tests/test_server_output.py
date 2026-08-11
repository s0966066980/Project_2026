import importlib.util
from pathlib import Path


def _server_module():
    path = Path(__file__).resolve().parents[1] / "r1_omni_server.py"
    spec = importlib.util.spec_from_file_location("r1_omni_server_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_native_output_is_normalized_for_admin_records():
    result = _server_module()._parse_output(
        "<think>The customer is smiling.</think><answer>happiness</answer>"
    )

    assert result == {
        "facial": "not_observed",
        "body": "",
        "vocal": "not_observed",
        "emotion": "開心",
        "intensity": "undetermined",
        "description": "The customer is smiling.",
    }


def test_json_output_keeps_all_supported_fields():
    result = _server_module()._parse_output(
        '```json\n{"emotion":"anger","intensity":"high","facial":"皺眉",'
        '"vocal":"音量提高","description":"顧客表現生氣。"}\n```'
    )

    assert result["emotion"] == "生氣"
    assert result["intensity"] == "high"
    assert result["facial"] == "皺眉"
    assert result["vocal"] == "音量提高"
    assert result["description"] == "顧客表現生氣。"


def test_unstructured_free_text_has_no_emotion_label():
    result = _server_module()._parse_output("A generic description without native tags")

    assert result["emotion"] == ""
    assert result["description"]
