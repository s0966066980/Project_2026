"""The published `/api/v1` contract must change only on purpose.

Three changes a consumer cannot absorb silently — a route disappearing, a field
being renamed, a field becoming required — all look like ordinary edits on the
server side and are only discovered by whoever calls the endpoint. The snapshot
turns each of them into a diff a reviewer sees and a test that fails until the
snapshot is regenerated in the same commit.

The distilled shape is committed rather than the full OpenAPI document: the
document carries FastAPI's rendering detail, and a snapshot that churns for
unrelated reasons stops being read.

Regenerate deliberately:

    python tools/generate_api_surface.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.integration]

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "tools" / "generate_api_surface.py"
SNAPSHOT = Path(__file__).resolve().parent / "contracts" / "api-v1-surface.json"


def _regenerate() -> str:
    assert GENERATOR.is_file(), f"generator missing at {GENERATOR}"
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
            "DATABASE_URL_FILE": "",
            "MIGRATION_DATABASE_URL_FILE": "",
        }
    )
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--stdout"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_published_surface_matches_the_committed_snapshot():
    committed = SNAPSHOT.read_text(encoding="utf-8")
    assert committed == _regenerate(), (
        f"{SNAPSHOT.relative_to(REPO_ROOT)} is stale. If the change is intended, run "
        "`python tools/generate_api_surface.py` and commit the diff with it."
    )


def test_the_snapshot_covers_the_whole_versioned_surface():
    """A snapshot of nothing compares equal to a surface of nothing."""

    surface = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert len(surface["operations"]) > 100, f"only {len(surface['operations'])} operations captured"
    assert len(surface["models"]) > 50, f"only {len(surface['models'])} models captured"
    assert all(
        key.startswith(("GET /api/v1/", "POST /api/v1/", "PUT /api/v1/", "PATCH /api/v1/", "DELETE /api/v1/"))
        for key in surface["operations"]
    )


def test_every_captured_model_records_its_fields_and_obligations():
    """Renames and new obligations are only visible if both lists are captured."""

    surface = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    for name, model in surface["models"].items():
        assert isinstance(model.get("properties"), list), name
        assert isinstance(model.get("required"), list), name
        assert set(model["required"]) <= set(model["properties"]), (
            f"{name} requires a field it does not publish: {sorted(set(model['required']) - set(model['properties']))}"
        )
