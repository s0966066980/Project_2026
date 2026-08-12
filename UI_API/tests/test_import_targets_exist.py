"""Every first-party import must name a module that exists.

A deferred import inside a function is invisible to the test suite until that
function runs, and some of them only run on a path the suite does not take. One
such import — `from repositories import commercial_settings_repository` inside
`config._load_settings_postgres` — survived a file move because the suite runs
on SQLite and never reaches the PostgreSQL settings branch. The whole stack
crash-looped on startup while the suite stayed green.

This resolves every first-party import target statically, at any nesting depth,
so a move that misses one fails here instead of in a container.
"""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.architecture]

UI_API_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = UI_API_ROOT / "backend"

# The packages that live under backend/, plus the top-level application modules.
FIRST_PARTY = {
    "ai_services",
    "api",
    "app_factory",
    "bootstrap",
    "capabilities",
    "config",
    "core",
    "database",
    "foundation",
    "integrations",
    "models",
    "modules",
    "project_analysis",
    "prompts",
    "realtime",
    "repositories",
    "routes",
    "scripts",
    "services",
    "shared",
    "utils",
}


def _python_files() -> list[Path]:
    """Everything on the application's import path, not just backend/.

    `config.py` sits at the UI_API root and holds the deferred import that took
    the stack down; a scan rooted at backend/ would have missed the very file
    this test exists for.
    """

    top_level = [path for path in UI_API_ROOT.glob("*.py") if path.name != "conftest.py"]
    return sorted([path for path in BACKEND_ROOT.rglob("*.py") if "__pycache__" not in path.parts] + top_level)


# main.py puts both UI_API/ and UI_API/backend/ on sys.path, so `config` and
# `backend.services.x` are both importable and both have to be searched.
SEARCH_ROOTS = (BACKEND_ROOT, UI_API_ROOT)


def _module_exists(dotted: str) -> bool:
    """True when the dotted path resolves to a module or package on sys.path."""

    relative = Path(*dotted.split("."))
    return any(
        (root / relative).with_suffix(".py").is_file() or (root / relative / "__init__.py").is_file()
        for root in SEARCH_ROOTS
    )


def _imported_targets(path: Path) -> list[tuple[int, str]]:
    """Every first-party module an import names, including inside functions."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FIRST_PARTY:
                    found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue  # relative imports resolve against a known package
            root = node.module.split(".")[0]
            if root not in FIRST_PARTY:
                continue
            found.append((node.lineno, node.module))
            # `from package import name`: unless the package's __init__ binds
            # that name, it has to be a submodule. Checking the submodule only
            # when it already exists would assert nothing.
            for alias in node.names:
                if alias.name == "*":
                    continue
                if _package_binds(node.module, alias.name):
                    continue
                found.append((node.lineno, f"{node.module}.{alias.name}"))
    return found


def _package_binds(dotted: str, name: str) -> bool:
    """True when the package's __init__ defines or re-exports `name` itself."""

    relative = Path(*dotted.split("."))
    for root in SEARCH_ROOTS:
        init = root / relative / "__init__.py"
        if init.is_file():
            source = init.read_text(encoding="utf-8")
            if "import *" in source:
                # The capability packages re-export their interface's __all__.
                # Resolving that statically would mean importing them; what may
                # be reached across a capability is the boundary test's job.
                return True
            return bool(source.strip()) and name in source
        if (root / relative).with_suffix(".py").is_file():
            # A plain module: everything it exposes is an attribute, not a module.
            return True
    return False


def test_every_first_party_import_target_exists():
    broken: list[str] = []
    for path in _python_files():
        relative = path.relative_to(UI_API_ROOT)
        for lineno, dotted in _imported_targets(path):
            if _module_exists(dotted):
                continue
            broken.append(f"{relative}:{lineno} -> {dotted}")
    assert broken == [], "imports naming modules that do not exist:\n  " + "\n  ".join(broken)


def test_the_scan_reaches_deferred_imports():
    """A scan that only sees module-scope imports would not have caught the outage."""

    deferred = 0
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    deferred += 1
                    break
    assert deferred > 20, f"only {deferred} functions carry imports; the scan may not be reaching them"
