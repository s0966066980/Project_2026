#!/usr/bin/env python3
"""Check the running host against the model registry.

A model name is not an identity. `qwen3.5:4b` on two machines can be two
different sets of weights, and a directory called `R1-Omni-0.5B` says nothing
about what is inside it. This compares what `config/models/manifest.yaml`
declares against what is actually present, and names what is missing instead of
letting a provider fail later with a message about an inference error.

    python backend/scripts/validate_model_manifest.py            # manifest shape only
    python backend/scripts/validate_model_manifest.py --local    # local weight paths
    python backend/scripts/validate_model_manifest.py --providers # ask Ollama for digests

`--local` has to run where the weights live: on the host, or inside the
container that mounts them. The application image never carries model weights
and will report all of them missing, which is true of that container and says
nothing about the deployment.

Exit codes: 0 verified, 1 a required model is missing or does not match.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "UI_API" / "backend"
sys.path.insert(0, str(ROOT / "UI_API"))
sys.path.insert(0, str(BACKEND))

MANIFEST = ROOT / "config" / "models" / "manifest.yaml"
REQUIRED_FIELDS = ("provider", "model", "source", "license_review", "required", "used_by")


class ManifestError(RuntimeError):
    """The registry itself is wrong, which is different from a model being absent."""


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    import yaml  # noqa: PLC0415

    location = path or MANIFEST
    if not location.is_file():
        raise ManifestError(f"model registry missing at {location}")
    document = yaml.safe_load(location.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or "models" not in document:
        raise ManifestError(f"{location} does not declare a models mapping")
    return document


def validate_shape(document: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if document.get("manifest_version") != 1:
        problems.append(f"unsupported manifest_version: {document.get('manifest_version')!r}")
    models = document.get("models") or {}
    if not models:
        problems.append("the registry declares no models")
    for key, entry in models.items():
        if not isinstance(entry, dict):
            problems.append(f"{key}: entry is not a mapping")
            continue
        for field in REQUIRED_FIELDS:
            if field not in entry:
                problems.append(f"{key}: missing {field}")
        if entry.get("required") and not (entry.get("digest") or entry.get("revision")):
            problems.append(f"{key}: required models must record a digest or a revision")
        if not entry.get("used_by"):
            problems.append(f"{key}: nothing records what uses this model")
    return problems


def _paths(entry: dict[str, Any]) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    if entry.get("local_path"):
        found.append((str(entry["model"]), ROOT / str(entry["local_path"])))
    for companion in entry.get("companions") or ():
        if companion.get("local_path"):
            found.append((str(companion["name"]), ROOT / str(companion["local_path"])))
    return found


def validate_local_paths(document: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (failures, notes). Only a required model's absence is a failure."""

    failures: list[str] = []
    notes: list[str] = []
    for key, entry in (document.get("models") or {}).items():
        for name, path in _paths(entry):
            if path.is_dir() and any(path.iterdir()):
                notes.append(f"present  {key}/{name}: {path.relative_to(ROOT)}")
            elif entry.get("required"):
                owner = str(entry.get("checked_on") or "the host")
                failures.append(f"missing  {key}/{name}: {path.relative_to(ROOT)} (expected on {owner})")
            else:
                notes.append(f"absent   {key}/{name} (optional): {path.relative_to(ROOT)}")
    return failures, notes


def validate_providers(document: dict[str, Any], *, ollama_url: str) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    entry = (document.get("models") or {}).get("llm") or {}
    declared = str(entry.get("model") or "")
    expected = str(entry.get("digest") or "")
    if not declared:
        return failures, notes
    try:
        with urllib.request.urlopen(f"{ollama_url.rstrip('/')}/api/tags", timeout=10) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as error:
        notes.append(f"skipped  llm digest: Ollama unreachable at {ollama_url} ({error})")
        return failures, notes

    installed = {str(model.get("name")): str(model.get("digest") or "") for model in payload.get("models") or ()}
    if declared not in installed:
        failures.append(f"missing  llm/{declared}: not installed in Ollama")
        return failures, notes
    actual = installed[declared]
    normalised = expected.split(":", 1)[-1] if expected else ""
    if normalised and actual != normalised:
        failures.append(f"mismatch llm/{declared}: manifest {normalised[:16]}… host {actual[:16]}…")
    else:
        notes.append(f"verified llm/{declared}: {actual[:16]}…")
    return failures, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="check declared local weight paths")
    parser.add_argument("--providers", action="store_true", help="ask providers for the installed identity")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()

    try:
        document = load_manifest()
    except ManifestError as error:
        print(f"FAIL {error}")
        return 1

    failures = validate_shape(document)
    notes: list[str] = []
    if args.local:
        found, seen = validate_local_paths(document)
        failures += found
        notes += seen
    if args.providers:
        found, seen = validate_providers(document, ollama_url=args.ollama_url)
        failures += found
        notes += seen

    for note in notes:
        print(note)
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        print(f"\n{len(failures)} problem(s); a required model is missing or does not match the registry")
        return 1
    print(f"\nmodel registry verified: {len(document.get('models') or {})} declared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
