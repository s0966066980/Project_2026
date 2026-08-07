import ast
from pathlib import Path

from backend.capabilities import CAPABILITIES

UI_API_ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES_ROOT = UI_API_ROOT / "backend" / "capabilities"
PLATFORM_ROOT = UI_API_ROOT / "backend" / "platform"
ALLOWED_CROSS_CAPABILITY_SURFACES = {"interface", "contracts", "events"}
LEGACY_LAYERS = {"repositories", "routes", "services"}


def _absolute_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_capability_manifest_is_unique_and_wave_ordered() -> None:
    keys = [capability.key for capability in CAPABILITIES]
    assert len(keys) == 10
    assert len(keys) == len(set(keys))
    assert [capability.migration_wave for capability in CAPABILITIES] == sorted(
        capability.migration_wave for capability in CAPABILITIES
    )


def test_capabilities_do_not_import_legacy_horizontal_layers() -> None:
    violations: list[str] = []
    for path in CAPABILITIES_ROOT.rglob("*.py"):
        for imported in _absolute_imports(path):
            parts = imported.split(".")
            if len(parts) >= 2 and parts[0] == "backend" and parts[1] in LEGACY_LAYERS:
                violations.append(f"{path.relative_to(UI_API_ROOT)} -> {imported}")
    assert violations == []


def test_cross_capability_imports_use_published_surfaces() -> None:
    violations: list[str] = []
    for path in CAPABILITIES_ROOT.rglob("*.py"):
        relative = path.relative_to(CAPABILITIES_ROOT)
        source_capability = relative.parts[0] if len(relative.parts) > 1 else ""
        for imported in _absolute_imports(path):
            parts = imported.split(".")
            if len(parts) < 3 or parts[:2] != ["backend", "capabilities"]:
                continue
            target_capability = parts[2]
            if not source_capability or target_capability == source_capability:
                continue
            published_surface = parts[3] if len(parts) > 3 else ""
            if published_surface not in ALLOWED_CROSS_CAPABILITY_SURFACES:
                violations.append(f"{relative} -> {imported}")
    assert violations == []


def test_platform_does_not_depend_on_business_capabilities() -> None:
    violations = [
        f"{path.relative_to(UI_API_ROOT)} -> {imported}"
        for path in PLATFORM_ROOT.rglob("*.py")
        for imported in _absolute_imports(path)
        if imported.startswith("backend.capabilities")
    ]
    assert violations == []
