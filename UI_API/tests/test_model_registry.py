"""The model registry has to describe the models this product actually runs.

A registry that drifts from the configuration is worse than none: it reads like
a guarantee while naming something nobody loads. These rules keep the declared
set and the configured set together, and check that the validator reports a
missing or mismatched model rather than passing quietly.
"""

import importlib.util
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.architecture]

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "config" / "models" / "manifest.yaml"
VALIDATOR = REPO_ROOT / "UI_API" / "backend" / "scripts" / "validate_model_manifest.py"


def _validator():
    spec = importlib.util.spec_from_file_location("validate_model_manifest", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_registry_is_well_formed():
    module = _validator()
    assert module.validate_shape(module.load_manifest()) == []


def test_every_model_the_compose_files_configure_is_declared():
    """A model configured but undeclared is a model nobody reviewed."""

    declared = {str(entry["model"]) for entry in _validator().load_manifest()["models"].values()}
    compose = (REPO_ROOT / "docker" / "compose.ai.yaml").read_text(encoding="utf-8")

    for configured in ("qwen3.5:4b", "BAAI/bge-small-zh-v1.5", "zh-TW-HsiaoChenNeural"):
        assert configured in compose, f"{configured} is no longer configured; update the registry"
        assert configured in declared, f"{configured} is configured but not declared in the model registry"


def test_required_models_carry_an_identity_not_just_a_name():
    """`qwen3.5:4b` on two machines can be two different sets of weights."""

    for key, entry in _validator().load_manifest()["models"].items():
        if entry.get("required"):
            assert entry.get("digest") or entry.get("revision"), f"{key} is required but has no digest or revision"


def test_the_emotion_model_declares_the_companions_it_cannot_load_without():
    """R1-Omni presents a missing companion as its own failure."""

    emotion = _validator().load_manifest()["models"]["emotion"]
    companions = {companion["name"] for companion in emotion["companions"]}
    assert companions == {"bert-base-uncased", "siglip-base-patch16-224", "whisper-large-v3"}


def test_a_missing_required_model_is_reported_rather_than_passed(tmp_path):
    module = _validator()
    document = module.load_manifest()
    document["models"]["emotion"]["local_path"] = "R1-Omni/models/not-installed"
    document["models"]["emotion"]["companions"] = []

    failures, _ = module.validate_local_paths(document)

    assert any("not-installed" in failure for failure in failures)


def test_an_absent_optional_model_is_not_a_failure():
    """Ordering continues without RAG; the registry must not claim otherwise."""

    module = _validator()
    document = module.load_manifest()
    document["models"]["rag_embedding"]["local_path"] = "does/not/exist"

    failures, notes = module.validate_local_paths(document)

    assert not any("does/not/exist" in failure for failure in failures)
    assert any("does/not/exist" in note for note in notes)


def test_a_registry_without_a_version_is_refused():
    module = _validator()
    document = module.load_manifest()
    document["manifest_version"] = 99

    assert any("manifest_version" in problem for problem in module.validate_shape(document))
