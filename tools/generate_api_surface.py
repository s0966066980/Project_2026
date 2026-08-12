#!/usr/bin/env python3
"""Emit a distilled snapshot of the published `/api/v1` contract.

The TypeScript generator beside this one covers one capability's DTOs. This
covers the shape of the whole versioned surface, so that the three changes a
consumer cannot absorb silently each fail a test instead of reaching a browser:

  - a route disappears,
  - a field is renamed,
  - a field becomes required that was not.

The full OpenAPI document is not committed: it carries FastAPI's rendering
detail, and a snapshot that changes for unrelated reasons stops being read.
What is committed is the part a client depends on.

Usage:
    python tools/generate_api_surface.py            # write the snapshot
    python tools/generate_api_surface.py --check    # fail if it would change
    python tools/generate_api_surface.py --stdout   # print, for use in a container
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "UI_API" / "tests" / "contracts" / "api-v1-surface.json"

METHODS = ("get", "post", "put", "patch", "delete")


def _find_ui_api_root() -> Path:
    candidates = [REPO_ROOT / "UI_API", Path.cwd(), *Path.cwd().parents]
    for candidate in candidates:
        if (candidate / "main.py").is_file() and (candidate / "backend").is_dir():
            return candidate
        nested = candidate / "UI_API"
        if (nested / "main.py").is_file() and (nested / "backend").is_dir():
            return nested
    raise SystemExit("could not locate UI_API/main.py from this working directory")


def _load_openapi() -> dict:
    # Pinned to the same substrate the contract tests use: the published schema
    # is a property of the code, not of whatever database the caller points at.
    os.environ.update(
        APP_ENV="test",
        DATABASE_BACKEND="sqlite",
        RUNTIME_DATA_ROOT=os.environ.get("RUNTIME_DATA_ROOT", "/tmp/project-2026-openapi"),
    )
    for leaked in ("DATABASE_URL", "MIGRATION_DATABASE_URL", "DATABASE_URL_FILE", "MIGRATION_DATABASE_URL_FILE"):
        os.environ[leaked] = ""

    ui_api_root = _find_ui_api_root()
    sys.path.insert(0, str(ui_api_root / "backend"))
    sys.path.insert(0, str(ui_api_root))
    from main import app  # noqa: PLC0415

    return app.openapi()


def _schema_name(node: Any) -> str:
    """Name the referenced component, following the wrappers FastAPI emits."""

    if not isinstance(node, dict):
        return ""
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return ref.rsplit("/", 1)[-1]
    for key in ("allOf", "anyOf", "oneOf"):
        for member in node.get(key) or ():
            found = _schema_name(member)
            if found:
                return found
    return ""


def _body_schema(operation: dict) -> str:
    content = (operation.get("requestBody") or {}).get("content") or {}
    return _schema_name((content.get("application/json") or {}).get("schema"))


def _response_schema(operation: dict) -> str:
    for status in ("200", "201"):
        content = ((operation.get("responses") or {}).get(status) or {}).get("content") or {}
        name = _schema_name((content.get("application/json") or {}).get("schema"))
        if name:
            return name
    return ""


def build_surface() -> dict:
    document = _load_openapi()
    schemas = document.get("components", {}).get("schemas", {})

    operations: dict[str, dict] = {}
    referenced: set[str] = set()
    for path, item in document.get("paths", {}).items():
        if not path.startswith("/api/v1/"):
            continue
        for method in METHODS:
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            body = _body_schema(operation)
            response = _response_schema(operation)
            referenced.update(name for name in (body, response) if name)
            operations[f"{method.upper()} {path}"] = {
                "operation_id": operation.get("operationId", ""),
                "request_schema": body,
                "response_schema": response,
                "parameters": sorted(
                    f"{parameter.get('in', '')}:{parameter.get('name', '')}{'!' if parameter.get('required') else ''}"
                    for parameter in operation.get("parameters") or ()
                ),
            }

    # Follow references one level at a time until the set stops growing, so a
    # DTO nested inside another published DTO is covered too.
    while True:
        discovered = set(referenced)
        for name in referenced:
            for node in _walk(schemas.get(name, {})):
                nested = _schema_name(node)
                if nested:
                    discovered.add(nested)
        if discovered == referenced:
            break
        referenced = discovered

    models = {}
    for name in sorted(referenced):
        schema = schemas.get(name)
        if not isinstance(schema, dict):
            continue
        models[name] = {
            "properties": sorted((schema.get("properties") or {}).keys()),
            "required": sorted(schema.get("required") or ()),
        }

    return {"operations": dict(sorted(operations.items())), "models": models}


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def render() -> str:
    return json.dumps(build_surface(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail instead of writing")
    parser.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = parser.parse_args()

    rendered = render()
    if args.stdout:
        sys.stdout.write(rendered)
        return 0
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != rendered:
            sys.stderr.write(f"{OUTPUT} is stale; run python tools/generate_api_surface.py\n")
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
