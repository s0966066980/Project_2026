import ast
from pathlib import Path

from backend.capabilities import CAPABILITIES

UI_API_ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES_ROOT = UI_API_ROOT / "backend" / "capabilities"
FOUNDATION_ROOT = UI_API_ROOT / "backend" / "foundation"
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


def test_boundary_roots_exist() -> None:
    """A directory that has been renamed away makes every rule over it pass vacuously.

    `backend/platform` was renamed to `backend/foundation` so it would stop
    shadowing the standard library, and the rule below kept pointing at the old
    path — `rglob` over a missing directory yields nothing, so it asserted
    nothing for as long as the rename has been in place.
    """

    assert CAPABILITIES_ROOT.is_dir()
    assert FOUNDATION_ROOT.is_dir()


def test_foundation_does_not_depend_on_business_capabilities() -> None:
    violations = [
        f"{path.relative_to(UI_API_ROOT)} -> {imported}"
        for path in FOUNDATION_ROOT.rglob("*.py")
        for imported in _absolute_imports(path)
        if imported.startswith("backend.capabilities")
    ]
    assert violations == []


CATALOG_OWNED_REPOSITORIES = {"menu_repository"}
# The capability's own service layer and transport, plus the composition root
# that binds the adapter, are the only places allowed to reach the tables
# directly until the repository itself moves inside the capability.
CATALOG_INTERNAL_PATHS = {
    "backend/repositories/menu_repository.py",
    "backend/services/menu_catalog_service.py",
    "backend/routes/menu_routes.py",
    "backend/bootstrap/container.py",
}


def test_catalog_tables_have_one_reader_surface() -> None:
    """Data authority means one owner, and an import is a way to acquire a second.

    Thirteen call sites across ordering, voice, member, promotion and
    recommendation used to import `menu_repository` directly. They now read
    through `capabilities.catalog`, so the ownership statement is enforced
    rather than asserted.
    """

    violations: list[str] = []
    for path in (UI_API_ROOT / "backend").rglob("*.py"):
        relative = str(path.relative_to(UI_API_ROOT))
        if relative in CATALOG_INTERNAL_PATHS or "__pycache__" in relative:
            continue
        for imported in _absolute_imports(path):
            leaf = imported.split(".")[-1]
            if leaf in CATALOG_OWNED_REPOSITORIES:
                violations.append(f"{relative} -> {imported}")
            if imported.endswith("repositories") and leaf == "repositories":
                source = path.read_text(encoding="utf-8")
                for owned in CATALOG_OWNED_REPOSITORIES:
                    if f"import {owned}" in source or f", {owned}" in source:
                        violations.append(f"{relative} -> repositories.{owned}")
    assert violations == []
