"""Architecture: module public API and import direction."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
MODULES = BACKEND / "modules"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_identity_module_exists_with_application_api() -> None:
    app = MODULES / "identity" / "application.py"
    assert app.is_file()
    text = app.read_text(encoding="utf-8")
    assert "login_admin" in text or "authorize_admin_action" in text


def test_modules_do_not_import_other_module_adapters() -> None:
    if not MODULES.is_dir():
        return
    offenders: list[str] = []
    for path in MODULES.rglob("*.py"):
        if "adapters" in path.parts:
            continue
        rel = path.relative_to(MODULES)
        owner = rel.parts[0]
        for imp in _imports(path):
            if not imp.startswith("modules."):
                continue
            parts = imp.split(".")
            if len(parts) >= 3 and parts[1] != owner and parts[2] == "adapters":
                offenders.append(f"{path}: {imp}")
    assert offenders == [], offenders
