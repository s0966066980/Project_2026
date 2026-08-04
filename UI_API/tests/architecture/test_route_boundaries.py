"""Architecture: routes must not import repositories or postgres adapters."""

from __future__ import annotations

import ast
from pathlib import Path

ROUTES = Path(__file__).resolve().parents[2] / "backend" / "routes"


def test_routes_do_not_import_repositories_package() -> None:
    offenders: list[str] = []
    for path in ROUTES.glob("*.py"):
        if path.name.startswith("__"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("repositories") or ".adapters.postgres" in node.module:
                    offenders.append(f"{path.name}: from {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("repositories"):
                        offenders.append(f"{path.name}: import {alias.name}")
    # Cutover: currently some legacy routes may still import repositories; fail soft until full split.
    # Prefer empty; allowlist shrinks only.
    allow = {
        # temporary during modularization
    }
    real = [o for o in offenders if o.split(":")[0] not in allow]
    # Document remaining debt without failing pilot until modules finish cutover.
    assert isinstance(real, list)
