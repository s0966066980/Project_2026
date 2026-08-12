"""The committed TypeScript contract must still be what the server publishes.

A hand-maintained frontend contract drifts silently: renaming a field on one
side breaks nothing until a customer hits it. Regenerating here and comparing
turns that into a failing test.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.integration]
REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "tools" / "generate_api_types.py"
GENERATED = REPO_ROOT / "UI_API" / "frontend" / "shared" / "contracts" / "api-v1-catalog.ts"


def test_generated_catalog_types_match_the_published_schema():
    if not GENERATOR.is_file():
        raise AssertionError(f"generator missing at {GENERATOR}")

    generator_env = os.environ.copy()
    generator_env.update(
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
        env=generator_env,
    )
    assert result.returncode == 0, result.stderr

    committed = GENERATED.read_text(encoding="utf-8")
    assert committed == result.stdout, (
        "UI_API/frontend/shared/contracts/api-v1-catalog.ts is stale; run `python tools/generate_api_types.py`"
    )


def test_the_generator_publishes_only_the_catalog_contract():
    """Generating every schema would ship internal request models to the browser.

    The set is pinned rather than pattern-matched: `ServicePeriodWindowDTO`
    belongs to the availability contract without carrying `Catalog` in its
    name, and a rule loose enough to admit it would also admit anything else.
    """

    source = GENERATOR.read_text(encoding="utf-8")
    exported = source.split("EXPORTED_SCHEMAS = (", 1)[1].split(")", 1)[0]
    names = {name.strip().strip('"') for name in exported.split(",") if name.strip()}
    assert names == {
        "CatalogItemDTO",
        "CatalogItemListDTO",
        "CatalogItemWriteDTO",
        "ServicePeriodWindowDTO",
        "CatalogAvailabilityRowDTO",
        "CatalogAvailabilityDTO",
        "CatalogAvailabilityCommandDTO",
    }
