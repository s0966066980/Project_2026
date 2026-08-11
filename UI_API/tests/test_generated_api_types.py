"""The committed TypeScript contract must still be what the server publishes.

A hand-maintained frontend contract drifts silently: renaming a field on one
side breaks nothing until a customer hits it. Regenerating here and comparing
turns that into a failing test.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "tools" / "generate_api_types.py"
GENERATED = REPO_ROOT / "UI_API" / "frontend" / "shared" / "contracts" / "api-v1-catalog.ts"


def test_generated_catalog_types_match_the_published_schema():
    if not GENERATOR.is_file():
        raise AssertionError(f"generator missing at {GENERATOR}")

    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--stdout"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    committed = GENERATED.read_text(encoding="utf-8")
    assert committed == result.stdout, (
        "UI_API/frontend/shared/contracts/api-v1-catalog.ts is stale; "
        "run `python tools/generate_api_types.py`"
    )


def test_the_generator_publishes_only_the_catalog_contract():
    """Generating every schema would ship internal request models to the browser."""

    source = GENERATOR.read_text(encoding="utf-8")
    assert "EXPORTED_SCHEMAS" in source
    exported = source.split("EXPORTED_SCHEMAS = (", 1)[1].split(")", 1)[0]
    assert all("Catalog" in name for name in exported.replace('"', "").split(",") if name.strip())
