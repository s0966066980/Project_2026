#!/usr/bin/env python3
"""Conservative unused-code scanner for Project_2026.

The report is intentionally biased toward false negatives. It only marks a file
as definitely unused when there is no known runtime entrypoint, import, HTML
reference, static import, or protected project rule keeping it alive.
"""

from __future__ import annotations

import ast
import json
import os
import re
import warnings
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_API = ROOT / "UI_API"
REPORTS = ROOT / "reports"

PROTECTED_FILES = {
    "README.md",
    "UI_API/README.md",
    "UI_API/PATENT_DESIGN.md",
    "UI_API/main.py",
    "UI_API/index.html",
    "UI_API/menu_data/menu.json",
    "Emotion-LLaMA/app_EmotionLlamaClient.py",
    "tools/analyze_unused_code.py",
    "tools/pos_interaction_demo_ui.py",
}

PROTECTED_STATIC_PREFIXES = {
    "UI_API/static/mcd_categories/",
    "UI_API/static/menu_images/",
}

PROTECTED_STATIC_FILES = {
    "UI_API/static/mcd_start.png",
}

PROTECTED_ENDPOINTS = {
    "/api/triggered_multimodal_analysis",
    "/api/interaction_event",
    "/api/barrier_state",
    "/api/intervention_result",
    "/api/ask",
    "/api/auto_recommend",
    "/api/customer_service",
    "/api/rag_status",
    "/api/menu",
    "/api/demo/trigger_scenario",
    "/api/debug/interaction_risk",
    "/api/debug/intervention_logs/{session_id}",
    "/ws/{client_type}/{session_id}",
}

RUNTIME_PATTERNS = [
    "UI_API/learning_data/",
    "UI_API/chroma_db/",
    "UI_API/chroma_db_versions/",
    "__pycache__/",
    ".pytest_cache/",
    "logs/",
    "tmp/",
    "temp/",
]

MODEL_SUFFIXES = {
    ".pt",
    ".pth",
    ".ckpt",
    ".safetensors",
    ".bin",
    ".gguf",
    ".onnx",
    ".h5",
    ".pb",
    ".tflite",
    ".engine",
    ".mlmodel",
    ".weights",
}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}
STATIC_SUFFIXES = IMAGE_SUFFIXES | {".css", ".js"}

warnings.filterwarnings("ignore", category=SyntaxWarning)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def all_files() -> list[Path]:
    ignored_parts = {".git", ".venv", "venv", "env", "ENV", "node_modules"}
    output = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignored_parts for part in path.parts):
            continue
        output.append(path)
    return sorted(output)


def is_runtime_file(path: Path) -> bool:
    r = rel(path)
    if r == "UI_API/learning_data/.gitkeep":
        return False
    if path.suffix in MODEL_SUFFIXES:
        return True
    return any(pattern in r for pattern in RUNTIME_PATTERNS) or r.endswith(".pyc") or r.endswith(".log")


def python_module_name(path: Path) -> str:
    r = rel(path)
    if not r.endswith(".py"):
        return ""
    if r.startswith("UI_API/"):
        r = r[len("UI_API/") :]
    elif r.startswith("tools/"):
        r = r[:-3]
        return r.replace("/", ".")
    elif r.startswith("Emotion-LLaMA/"):
        r = r[:-3]
        return r.replace("/", ".")
    else:
        r = r[:-3]
    if r.endswith("/__init__"):
        r = r[: -len("/__init__")]
    return r.replace("/", ".")


def scan_python(files: list[Path]) -> dict:
    module_to_file = {}
    imports = defaultdict(set)
    definitions = defaultdict(list)
    include_router_refs = set()
    route_defs = []
    parse_errors = {}

    py_files = [p for p in files if p.suffix == ".py"]
    for path in py_files:
        mod = python_module_name(path)
        if mod:
            module_to_file[mod] = rel(path)

    for path in py_files:
        r = rel(path)
        source = read_text(path)
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            parse_errors[r] = str(exc)
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[r].add(alias.name)
                    imports[r].add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports[r].add(node.module)
                    imports[r].add(node.module.split(".")[0])
                    for alias in node.names:
                        imports[r].add(f"{node.module}.{alias.name}")
                else:
                    for alias in node.names:
                        imports[r].add(alias.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions[r].append(
                    {
                        "name": node.name,
                        "type": node.__class__.__name__,
                        "lineno": getattr(node, "lineno", 0),
                    }
                )
            elif isinstance(node, ast.Call):
                attr = getattr(node.func, "attr", "")
                if attr == "include_router" and node.args:
                    include_router_refs.add(ast.unparse(node.args[0]) if hasattr(ast, "unparse") else "")

        for match in re.finditer(r"@router\.(get|post|put|delete|patch|websocket)\(([^)]*)\)", source):
            raw = match.group(2)
            endpoint_match = re.search(r"['\"]([^'\"]+)['\"]", raw)
            if not endpoint_match:
                continue
            prefix = ""
            prefix_match = re.search(r"APIRouter\(\s*prefix=['\"]([^'\"]+)['\"]", source)
            if prefix_match:
                prefix = prefix_match.group(1)
            endpoint = endpoint_match.group(1)
            route_defs.append(
                {
                    "file": r,
                    "method": match.group(1),
                    "path": f"{prefix}{endpoint}" if endpoint.startswith("/") else f"{prefix}/{endpoint}",
                    "lineno": source[: match.start()].count("\n") + 1,
                }
            )

    referenced_modules = set()
    for mods in imports.values():
        referenced_modules.update(mods)

    return {
        "module_to_file": module_to_file,
        "imports": {k: sorted(v) for k, v in imports.items()},
        "definitions": dict(definitions),
        "include_router_refs": sorted(include_router_refs),
        "referenced_modules": sorted(referenced_modules),
        "route_defs": route_defs,
        "parse_errors": parse_errors,
    }


def scan_frontend(files: list[Path]) -> dict:
    index = UI_API / "index.html"
    index_text = read_text(index)
    static_refs = set()
    dom_ids = set()
    dom_classes = set()

    for pattern in [r"(?:src|href)=['\"]([^'\"]+)['\"]", r"url\(['\"]?([^'\")]+)"]:
        for match in re.finditer(pattern, index_text):
            static_refs.add(match.group(1).split("?")[0])

    for match in re.finditer(r"\bid=['\"]([^'\"]+)['\"]", index_text):
        dom_ids.add(match.group(1))
    for match in re.finditer(r"\bclass=['\"]([^'\"]+)['\"]", index_text):
        dom_classes.update(match.group(1).split())

    js_imports = defaultdict(set)
    api_paths = set()
    ws_events = set()
    js_text_all = ""
    for path in UI_API.glob("static/*.js"):
        text = read_text(path)
        js_text_all += "\n" + text
        r = rel(path)
        for match in re.finditer(r"from\s+['\"]([^'\"]+)['\"]|import\(\s*['\"]([^'\"]+)['\"]\s*\)", text):
            target = (match.group(1) or match.group(2) or "").split("?")[0]
            js_imports[r].add(target)
        for match in re.finditer(r"API_BASE\}\s*/api/([^`'\"]+)|['\"](/api/[^'\"`]+)['\"]|`[^`]*(/api/[^`]+)`", text):
            raw = next((g for g in match.groups() if g), "")
            if raw and not raw.startswith("/api/"):
                raw = "/api/" + raw
            if raw:
                api_paths.add(re.sub(r"\$\{[^}]+\}", "{param}", raw).rstrip("`"))
        for match in re.finditer(r"['\"]([a-z_]+(?:_[a-z]+)+)['\"]", text):
            token = match.group(1)
            if token in {
                "interaction_intervention",
                "customer_service_request",
                "human_reply",
                "emotion_analysis_started",
                "emotion_analysis_completed",
                "settings_changed",
                "staff_notify",
                "demo_event",
            }:
                ws_events.add(token)

    return {
        "index_static_refs": sorted(static_refs),
        "dom_ids": sorted(dom_ids),
        "dom_classes": sorted(dom_classes),
        "js_imports": {k: sorted(v) for k, v in js_imports.items()},
        "api_paths": sorted(api_paths),
        "websocket_event_names": sorted(ws_events),
        "all_js_text": js_text_all,
    }


def normalize_static_ref(value: str) -> str:
    if value.startswith("/"):
        value = value[1:]
    return value


def analyze() -> dict:
    files = all_files()
    py = scan_python(files)
    fe = scan_frontend(files)

    all_text = "\n".join(read_text(p) for p in files if p.suffix in {".py", ".js", ".html", ".css", ".md", ".json"})
    tracked_like_runtime = [rel(p) for p in files if is_runtime_file(p)]

    included_route_files = {
        "UI_API/routes/core_routes.py",
        "UI_API/routes/menu_routes.py",
        "UI_API/routes/rag_routes.py",
        "UI_API/routes/voice_routes.py",
        "UI_API/routes/customer_service_routes.py",
        "UI_API/routes/recommendation_routes.py",
        "UI_API/routes/emotion_routes.py",
        "UI_API/routes/interaction_routes.py",
        "UI_API/routes/multimodal_routes.py",
        "UI_API/routes/demo_routes.py",
        "UI_API/routes/realtime_routes.py",
        "UI_API/routes/debug_routes.py",
    }

    referenced_static = {normalize_static_ref(item) for item in fe["index_static_refs"]}
    for imports in fe["js_imports"].values():
        for item in imports:
            if item.startswith("./"):
                referenced_static.add("UI_API/static/" + item[2:])
    for match in re.finditer(r"['\"](/static/[^'\"]+)['\"]", all_text):
        referenced_static.add(normalize_static_ref(match.group(1)))
    for match in re.finditer(r"url\(['\"]?(/static/[^'\")]+)", all_text):
        referenced_static.add(normalize_static_ref(match.group(1)))

    definitely_unused_files = []
    maybe_unused_files = []
    unused_static_assets = []
    keep_static_assets = []

    for path in files:
        r = rel(path)
        if r in PROTECTED_FILES or r in included_route_files:
            continue
        if is_runtime_file(path):
            continue
        if r.startswith("UI_API/static/") and path.suffix in STATIC_SUFFIXES:
            if (
                r in {"UI_API/static/app.js", "UI_API/static/styles.css"}
                or r in PROTECTED_STATIC_FILES
                or any(r.startswith(prefix) for prefix in PROTECTED_STATIC_PREFIXES)
                or r in referenced_static
            ):
                keep_static_assets.append(r)
            elif path.suffix == ".js":
                text = read_text(path).strip()
                if text.startswith("// Reserved for the next phase"):
                    definitely_unused_files.append(r)
                else:
                    maybe_unused_files.append({"file": r, "reason": "static JS is not referenced by index.html or module imports"})
            elif path.name.startswith("menu_M0"):
                definitely_unused_files.append(r)
                unused_static_assets.append(r)
            else:
                unused_static_assets.append(r)
                maybe_unused_files.append({"file": r, "reason": "static asset not referenced by HTML/CSS/JS string scan"})
        elif path.suffix == ".py":
            mod = python_module_name(path)
            base = mod.split(".")[-1] if mod else path.stem
            if r.startswith("UI_API/routes/") and r not in included_route_files and r != "UI_API/routes/__init__.py":
                maybe_unused_files.append({"file": r, "reason": "route file is not included by main.py"})
            elif mod and mod not in py["referenced_modules"] and base not in all_text.replace(read_text(path), ""):
                if r in {"Emotion-LLaMA/app.py", "Emotion-LLaMA/app_20260120.py"}:
                    maybe_unused_files.append({"file": r, "reason": "alternate Emotion-LLaMA entrypoint; keep until manually verified"})
                elif r == "UI_API/gemini_direct_chat.py":
                    maybe_unused_files.append({"file": r, "reason": "manual diagnostic script; not imported by app"})
                elif not r.endswith("__init__.py"):
                    maybe_unused_files.append({"file": r, "reason": "python module not imported by static scan"})

    used_route_paths = set()
    for api_path in fe["api_paths"]:
        used_route_paths.add(api_path.split("?")[0])
    unused_routes = []
    for route in py["route_defs"]:
        path = route["path"]
        if route.get("file") == "UI_API/routes/debug_routes.py":
            continue
        if path in PROTECTED_ENDPOINTS:
            continue
        if any(path.startswith(prefix.rstrip("{param}")) for prefix in used_route_paths):
            continue
        if "{" in path:
            static_prefix = path.split("{", 1)[0].rstrip("/")
            if any(item.startswith(static_prefix) for item in used_route_paths):
                continue
        if path in {"/", "/pos", "/admin", "/customer", "/demo-tool"}:
            continue
        unused_routes.append(route)

    name_counts = defaultdict(int)
    for path in files:
        if path.suffix in {".py", ".js", ".html"}:
            text = read_text(path)
            for rfile, defs in py["definitions"].items():
                for item in defs:
                    name_counts[item["name"]] += len(re.findall(r"\b" + re.escape(item["name"]) + r"\b", text))

    unused_functions = []
    for rfile, defs in py["definitions"].items():
        if rfile.startswith("Emotion-LLaMA/minigpt4/"):
            continue
        if rfile.startswith("UI_API/routes/"):
            continue
        for item in defs:
            name = item["name"]
            if name.startswith("__") or name in {"create_router", "main"}:
                continue
            if name_counts[name] <= 1:
                unused_functions.append({"file": rfile, **item, "reason": "definition name appears only once in scanned source"})

    report = {
        "definitely_unused_files": sorted(set(definitely_unused_files)),
        "maybe_unused_files": sorted(maybe_unused_files, key=lambda item: item["file"]),
        "unused_functions": sorted(unused_functions, key=lambda item: (item["file"], item["lineno"])),
        "unused_routes": sorted(unused_routes, key=lambda item: (item["file"], item["lineno"])),
        "unused_static_assets": sorted(set(unused_static_assets)),
        "runtime_data_files": sorted(set(tracked_like_runtime)),
        "external_entrypoints_to_keep": sorted(
            {
                "UI_API/main.py",
                "UI_API/index.html",
                "UI_API/menu_data/menu.json",
                "Emotion-LLaMA/app_EmotionLlamaClient.py",
                "tools/pos_interaction_demo_ui.py",
                "/api/triggered_multimodal_analysis",
                "/api/interaction_event",
                "/api/barrier_state",
                "/api/intervention_result",
                "/api/ask",
                "/api/auto_recommend",
                "/api/customer_service",
                "/api/rag_status",
                "/api/debug/interaction_risk",
                "/api/debug/intervention_logs/{session_id}",
                "/demo-tool",
            }
        ),
        "safe_to_delete_static_assets": sorted(set(definitely_unused_files) & set(unused_static_assets)),
        "maybe_used_static_assets": sorted(set(item["file"] for item in maybe_unused_files if item["file"].startswith("UI_API/static/"))),
        "keep_static_assets": sorted(set(keep_static_assets)),
        "python_parse_errors": py["parse_errors"],
        "frontend_api_paths": fe["api_paths"],
        "websocket_event_names": fe["websocket_event_names"],
        "frontend_split_plan": [
            {
                "phase": 1,
                "title": "Keep current app.js runtime behavior",
                "scope": "Do not split POS/Admin code in this cleanup pass; app.js still owns boot mode selection, shared state, and legacy-safe event wiring.",
            },
            {
                "phase": 2,
                "title": "Extract admin-only panels",
                "scope": "Move settings, logs, RAG admin, and statistics renderers behind a static/admin module after route/API smoke tests are stable.",
            },
            {
                "phase": 3,
                "title": "Extract POS interaction pipeline",
                "scope": "Move POS event capture, risk trigger handling, media-buffer trigger calls, and checkout feedback into a static/pos_interaction module.",
            },
            {
                "phase": 4,
                "title": "Keep shared utilities small",
                "scope": "Keep API wrapper, cart helpers, realtime client, media buffer, and UI primitives as shared modules; avoid moving business decisions into frontend.",
            },
        ],
    }
    return report


def write_reports(report: dict) -> None:
    REPORTS.mkdir(exist_ok=True)
    json_path = REPORTS / "unused_code_report.json"
    md_path = REPORTS / "unused_code_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# Unused Code Report", ""]
    for key in [
        "definitely_unused_files",
        "maybe_unused_files",
        "unused_functions",
        "unused_routes",
        "unused_static_assets",
        "runtime_data_files",
        "safe_to_delete_static_assets",
        "maybe_used_static_assets",
        "keep_static_assets",
        "external_entrypoints_to_keep",
        "frontend_split_plan",
    ]:
        lines.extend([f"## {key}", ""])
        value = report.get(key, [])
        if not value:
            lines.extend(["- None", ""])
            continue
        for item in value:
            if isinstance(item, dict):
                lines.append("- " + json.dumps(item, ensure_ascii=False, sort_keys=True))
            else:
                lines.append(f"- `{item}`")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    report = analyze()
    write_reports(report)
    print(json.dumps({
        "definitely_unused_files": len(report["definitely_unused_files"]),
        "maybe_unused_files": len(report["maybe_unused_files"]),
        "unused_functions": len(report["unused_functions"]),
        "unused_routes": len(report["unused_routes"]),
        "runtime_data_files": len(report["runtime_data_files"]),
        "reports": [
            "reports/unused_code_report.md",
            "reports/unused_code_report.json",
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
