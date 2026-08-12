"""The marker taxonomy has to select tests, not decorate them.

Fourteen markers were declared in `pyproject.toml` and none were ever applied,
so `pytest -m unit` and `pytest -m integration` each collected nothing while
looking like a working selection. A CI job split built on that would have
reported green without running a single test.

These rules keep every test reachable through a layer marker, and keep the
declared set and the applied set from drifting apart again.
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.architecture]

UI_API_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = UI_API_ROOT / "tests"

# A test file must be reachable by at least one of these. The rest of the
# declared markers (postgres, redis, hardware) describe what a test needs from
# the environment and are additive.
LAYER_MARKERS = {"unit", "contract", "architecture", "security", "integration", "slow"}

# pytest ships these; they are not the project's taxonomy and are not declared.
BUILTIN_MARKERS = {
    "filterwarnings",
    "parametrize",
    "skip",
    "skipif",
    "usefixtures",
    "xfail",
}


def _declared_markers() -> set[str]:
    """Read the declared marker names without a TOML parser.

    `tomllib` arrived in 3.11 and the runtime is 3.10, so the block is read
    directly rather than adding a dependency for eight strings.
    """

    source = (UI_API_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^markers = \[(.*?)^\]", source, re.MULTILINE | re.DOTALL)
    assert block, "pyproject.toml no longer declares a markers list"
    return {name for name in re.findall(r'"([a-z_]+):', block.group(1))}


def _module_markers(path: Path) -> set[str]:
    """Read `pytestmark` without importing the module."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        for attribute in ast.walk(node.value):
            if isinstance(attribute, ast.Attribute) and isinstance(attribute.value, ast.Attribute):
                if getattr(attribute.value.value, "id", "") == "pytest" and attribute.value.attr == "mark":
                    found.add(attribute.attr)
    return found - BUILTIN_MARKERS


def _test_files() -> list[Path]:
    return sorted(TESTS_ROOT.glob("test_*.py"))


def test_every_test_file_carries_a_layer_marker() -> None:
    unmarked = [path.name for path in _test_files() if not (_module_markers(path) & LAYER_MARKERS)]
    assert unmarked == [], f"add a layer marker to: {unmarked}"


def test_applied_markers_are_all_declared() -> None:
    declared = _declared_markers()
    applied: set[str] = set()
    for path in _test_files():
        applied |= _module_markers(path)
    assert applied <= declared, f"undeclared markers in use: {sorted(applied - declared)}"


def test_no_declared_marker_is_decoration() -> None:
    """A declared marker with no tests behind it is the failure this file exists for.

    `hardware` is the deliberate exception: the target Kiosk does not exist yet,
    and `pytest -m "not hardware"` has to keep working before the first such
    test is written.
    """

    declared = _declared_markers() - {"hardware"}
    applied: set[str] = set()
    for path in _test_files():
        applied |= _module_markers(path)
    assert declared <= applied, f"declared but never applied: {sorted(declared - applied)}"


def test_each_layer_selects_a_non_empty_set() -> None:
    by_layer = {marker: [] for marker in LAYER_MARKERS}
    for path in _test_files():
        for marker in _module_markers(path) & LAYER_MARKERS:
            by_layer[marker].append(path.name)
    empty = sorted(marker for marker, files in by_layer.items() if not files)
    assert empty == [], f"layer markers that select nothing: {empty}"


def test_the_readme_documents_how_to_select_a_layer() -> None:
    """A taxonomy nobody can find is a taxonomy nobody uses."""

    readme = (UI_API_ROOT / "README.md").read_text(encoding="utf-8")
    assert "pytest -m" in readme
    for marker in sorted(LAYER_MARKERS):
        assert re.search(rf"\b{marker}\b", readme), f"README does not mention the {marker} layer"
