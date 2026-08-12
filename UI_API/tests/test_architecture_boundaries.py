import ast
import re
from pathlib import Path

import pytest

from backend.capabilities import CAPABILITIES

pytestmark = [pytest.mark.architecture]
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


def _module_parts(imported: str) -> list[str]:
    """Normalise an import to the package path the application actually writes.

    `main.py` puts `backend/` on `sys.path`, so application modules import
    `services.x`, never `backend.services.x`. Both rules below required the
    `backend.` prefix, which no application file has ever written: they walked
    every capability file and could not match a single import, so they asserted
    nothing while eight real violations sat in the tree. Tests do import
    `backend.capabilities`, so the prefix is stripped rather than rejected.
    """

    parts = imported.split(".")
    return parts[1:] if parts[:1] == ["backend"] else parts


# Capability interfaces that still reach into the legacy horizontal layers.
# Each entry is a capability that has not taken ownership of its own data, so
# the execution plan still counts it against the Module Independence Gate.
# This list may only shrink: a converged capability is deleted from it, and a
# new one may never be added.
CAPABILITIES_STILL_ON_LEGACY_LAYERS = {
    "backend/capabilities/member/interface.py",
    "backend/capabilities/operations_configuration/interface.py",
    "backend/capabilities/ordering/interface.py",
    "backend/capabilities/recommendation_analytics/interface.py",
}


def test_capabilities_do_not_import_legacy_horizontal_layers() -> None:
    violations: list[str] = []
    unused_entries = set(CAPABILITIES_STILL_ON_LEGACY_LAYERS)
    for path in CAPABILITIES_ROOT.rglob("*.py"):
        relative = str(path.relative_to(UI_API_ROOT))
        for imported in _absolute_imports(path):
            parts = _module_parts(imported)
            if not parts or parts[0] not in LEGACY_LAYERS:
                continue
            unused_entries.discard(relative)
            if relative not in CAPABILITIES_STILL_ON_LEGACY_LAYERS:
                violations.append(f"{relative} -> {imported}")
    assert violations == []
    assert unused_entries == set(), f"no longer on legacy layers; remove from the list: {sorted(unused_entries)}"


def test_cross_capability_imports_use_published_surfaces() -> None:
    violations: list[str] = []
    for path in CAPABILITIES_ROOT.rglob("*.py"):
        relative = path.relative_to(CAPABILITIES_ROOT)
        source_capability = relative.parts[0] if len(relative.parts) > 1 else ""
        for imported in _absolute_imports(path):
            parts = _module_parts(imported)
            if len(parts) < 2 or parts[0] != "capabilities":
                continue
            target_capability = parts[1]
            if not source_capability or target_capability == source_capability:
                continue
            published_surface = parts[2] if len(parts) > 2 else ""
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


def test_every_manifest_capability_has_a_published_package() -> None:
    missing = []
    for capability in CAPABILITIES:
        package = CAPABILITIES_ROOT / capability.key
        if not all((package / name).is_file() for name in ("__init__.py", "contracts.py", "interface.py")):
            missing.append(capability.key)
    assert missing == []


def test_foundation_does_not_depend_on_business_capabilities() -> None:
    violations = [
        f"{path.relative_to(UI_API_ROOT)} -> {imported}"
        for path in FOUNDATION_ROOT.rglob("*.py")
        for imported in _absolute_imports(path)
        if _module_parts(imported)[:1] == ["capabilities"]
    ]
    assert violations == []


CATALOG_OWNED_REPOSITORIES = {"menu_repository"}
# The capability's own service layer and transport, plus the composition root
# that binds the adapter, are the only places allowed to reach the tables
# directly until the repository itself moves inside the capability.
CATALOG_INTERNAL_PATHS = {
    "backend/repositories/menu_repository.py",
    "backend/services/menu_catalog_service.py",
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


def test_catalog_has_no_legacy_transport_or_frontend_consumer() -> None:
    """The measured compatibility window is closed for repository-owned clients."""

    assert not (UI_API_ROOT / "backend" / "routes" / "menu_routes.py").exists()
    assert not (UI_API_ROOT / "backend" / "routes" / "availability_routes.py").exists()

    forbidden = ("/api/menu", "/api/availability")
    violations = [
        f"{path.relative_to(UI_API_ROOT)} -> {literal}"
        for root in (
            UI_API_ROOT / "frontend" / "admin",
            UI_API_ROOT / "frontend" / "kiosk",
            UI_API_ROOT / "frontend" / "shared",
        )
        for path in root.rglob("*.js")
        for literal in forbidden
        if literal in path.read_text(encoding="utf-8")
    ]
    assert violations == []


def test_frontend_feature_code_uses_shared_transport_only() -> None:
    violations = []
    for root_name in ("admin", "kiosk"):
        root = UI_API_ROOT / "frontend" / root_name
        for path in root.rglob("*.js"):
            source = path.read_text(encoding="utf-8")
            code_lines = [line for line in source.splitlines() if not line.lstrip().startswith(("//", "*"))]
            if any("fetch(" in line for line in code_lines) and "shared/httpClient.js" not in source:
                violations.append(str(path.relative_to(UI_API_ROOT)))
    assert violations == []


def test_frontend_feature_code_has_one_versioned_client_owner() -> None:
    """Static source serving must not reintroduce feature-level v1 URLs."""

    client = UI_API_ROOT / "frontend" / "shared" / "api" / "v1Client.js"
    assert client.exists(), "the static runtime needs a directly-served JS client entrypoint"
    violations = []
    for root_name in ("admin", "kiosk"):
        root = UI_API_ROOT / "frontend" / root_name
        for path in root.rglob("*.js"):
            source = path.read_text(encoding="utf-8")
            code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith(("//", "*")))
            if re.search(r"[\"'`]\/api\/v1(?:[/?`\"'])", code):
                violations.append(str(path.relative_to(UI_API_ROOT)))
    assert violations == []
