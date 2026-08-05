import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))

import r1_omni_server
from humanomni.model.humanomni_arch import resolve_bert_model_path


def test_runtime_model_config_provides_portable_bert_path(tmp_path, monkeypatch):
    model_root = tmp_path / "models"
    model_source = model_root / "R1-Omni-0.5B"
    bert_path = model_root / "bert-base-uncased"
    vision_path = model_root / "siglip-base-patch16-224"
    audio_path = model_root / "whisper-large-v3"

    model_source.mkdir(parents=True)
    bert_path.mkdir()
    vision_path.mkdir()
    audio_path.mkdir()
    (model_source / "config.json").write_text("{}", encoding="utf-8")
    (model_source / "model.safetensors").write_bytes(b"model")
    (bert_path / "vocab.txt").write_text("token", encoding="utf-8")
    (vision_path / "config.json").write_text("{}", encoding="utf-8")
    (vision_path / "model.safetensors").write_bytes(b"vision")
    (audio_path / "config.json").write_text("{}", encoding="utf-8")
    (audio_path / "model.safetensors").write_bytes(b"audio")

    monkeypatch.setattr(r1_omni_server, "MODEL_SOURCE_PATH", model_source)
    monkeypatch.setattr(r1_omni_server, "BERT_PATH", bert_path)
    monkeypatch.setattr(r1_omni_server, "VISION_PATH", vision_path)
    monkeypatch.setattr(r1_omni_server, "AUDIO_PATH", audio_path)
    monkeypatch.setattr(r1_omni_server, "_runtime_model_dir", None)

    runtime_config = json.loads(
        (r1_omni_server.Path(r1_omni_server._portable_model_path()) / "config.json").read_text(
            encoding="utf-8"
        )
    )

    assert runtime_config["mm_bert_model"] == str(bert_path)
    assert resolve_bert_model_path(SimpleNamespace(**runtime_config)) == str(bert_path)
