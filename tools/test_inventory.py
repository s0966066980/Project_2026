#!/usr/bin/env python3
"""Scan repository tests and classify them for the Local-first program.

Outputs JSON to stdout (or --json path) and optional markdown summary.
Does not modify production code. No secrets/PII.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND_TESTS = REPO / "UI_API" / "tests"
FRONTEND_TESTS = REPO / "UI_API" / "frontend" / "tests"
TDD_DIR = REPO / ".github" / "tdd"
DEPLOY_DIR = REPO / "deploy"
SCRIPTS_DIR = REPO / "scripts"
OPS_DIR = REPO / "docs" / "operations"

MARKER_RE = re.compile(r"@pytest\.mark\.(\w+)|pytest\.mark\.(\w+)")
DOCKER_RE = re.compile(r"\bdocker\b|Dockerfile|compose\.ya?ml|docker-compose", re.I)
DOC_ONLY_HINTS = (
    "read_text",
    "Path(__file__)",
    ".md",
    "ARCHITECTURE",
    "FUTURE_MODULES",
    "assert \"",
    "assert '",
    "in source",
    "in text",
    "in sql",
    "in workflow",
)
INTEGRATION_HINTS = (
    "postgres",
    "DATABASE_URL",
    "redis",
    "REDIS_URL",
    "psycopg",
    "playwright",
    "e2e",
    "TestClient",
)
FILE_ONLY_HINTS = (
    "is_file()",
    "exists()",
    "path.name",
    "migration_files",
    "CREATE TABLE",
    "assert path",
)


@dataclass
class TestFunction:
    file: str
    name: str
    lineno: int
    markers: list[str] = field(default_factory=list)
    body_hash: str = ""
    body_lines: int = 0
    classification: str = "KEEP_CORE"
    tier: str = "1"
    notes: str = ""
    is_integration: bool = False
    is_doc_or_file_only: bool = False


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def _body_source(node: ast.AST, source: str) -> str:
    try:
        return ast.get_source_segment(source, node) or ""
    except Exception:
        return ""


def _classify(file_rel: str, name: str, body: str, markers: list[str]) -> tuple[str, str, str, bool, bool]:
    lower = body.lower()
    file_l = file_rel.lower()
    name_l = name.lower()
    notes: list[str] = []

    is_integration = any(h.lower() in lower or h.lower() in file_l for h in INTEGRATION_HINTS)
    if "postgres" in file_l or file_l.startswith("ui_api/tests/postgres_"):
        is_integration = True
    if any(m in {"integration", "e2e", "postgres", "redis"} for m in markers):
        is_integration = True

    file_only = False
    if any(h in body for h in FILE_ONLY_HINTS) and body.count("assert") <= 4:
        # Likely structural/file presence rather than behavior
        if "pytest.raises" not in body and "client." not in lower and "service." not in lower:
            file_only = True
            notes.append("file/sql structure asserts")

    doc_only = False
    if any(h in body for h in DOC_ONLY_HINTS) and "def test_" in f"def {name}":
        if "http" not in lower and "client" not in lower and "service" not in lower:
            if body.count("assert") <= 8 and len(body) < 1200:
                doc_only = True
                notes.append("doc/string content asserts")

    # Core risk retention
    core_keywords = (
        "auth",
        "permission",
        "scope",
        "checkout",
        "idempoten",
        "member",
        "pii",
        "worker",
        "outbox",
        "migration",
        "security",
        "session",
        "token",
        "pricing",
        "transition",
    )
    is_core = any(k in name_l or k in file_l for k in core_keywords)

    classification = "KEEP_CORE"
    tier = "1"
    if is_integration:
        classification = "KEEP_INTEGRATION"
        tier = "3"
        notes.append("integration dependency")
    elif file_only or doc_only:
        classification = "REMOVE_REDUNDANT" if file_only or doc_only else classification
        tier = "4"
        if doc_only and not file_only:
            classification = "MOVE_EXTENDED"
    elif "tdd" in file_l or "documentation" in name_l or "roadmap" in name_l:
        classification = "MOVE_EXTENDED"
        tier = "4"
        notes.append("documentation/tdd evidence style")
    elif any(k in name_l for k in ("dataclass", "protocol", "exists", "filename", "migration_is")):
        classification = "REMOVE_REDUNDANT"
        tier = "4"
        notes.append("trivial existence/name test candidate")
    elif is_core:
        classification = "KEEP_CORE"
        tier = "1" if any(k in name_l for k in ("auth", "security", "scope", "checkout", "smoke")) else "2"
    else:
        classification = "KEEP_CORE"
        tier = "2"

    # External-not-local signals
    if any(k in file_l or k in name_l for k in ("payment", "s3", "cloud", "telemetry", "pos_adapter")):
        if "fake" in name_l or "contract" in name_l:
            classification = "KEEP_CORE"
            notes.append("local fake/contract retained")
        else:
            notes.append("external-adjacent")

    if "docker" in lower or "compose" in lower:
        classification = "REMOVE_REDUNDANT"
        tier = "4"
        notes.append("docker-specific")

    return classification, tier, "; ".join(notes), is_integration, file_only or doc_only


def collect_python_tests(root: Path) -> list[TestFunction]:
    results: list[TestFunction] = []
    if not root.exists():
        return results
    for path in sorted(root.rglob("*.py")):
        if path.name.startswith(".") or "__pycache__" in path.parts:
            continue
        if not (path.name.startswith("test_") or path.name.endswith("_test.py") or path.name.startswith("postgres_")):
            # include integration modules that define tests without test_ prefix naming on file
            text_probe = path.read_text(encoding="utf-8", errors="replace")
            if "def test_" not in text_probe:
                continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            results.append(
                TestFunction(
                    file=_rel(path),
                    name=f"<syntax_error:{exc.lineno}>",
                    lineno=exc.lineno or 0,
                    classification="KEEP_CORE",
                    tier="0",
                    notes=f"syntax error: {exc.msg}",
                )
            )
            continue
        file_markers = [m for m in MARKER_RE.findall(source) for m in m if m]
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            body = _body_source(node, source) or ""
            markers = []
            for dec in node.decorator_list:
                dec_src = ast.get_source_segment(source, dec) or ""
                markers.extend([m for pair in MARKER_RE.findall(dec_src) for m in pair if m])
            markers = sorted(set(markers + file_markers))
            body_hash = hashlib.sha256(re.sub(r"\s+", " ", body).strip().encode()).hexdigest()[:16]
            classification, tier, notes, is_int, is_doc = _classify(_rel(path), node.name, body, markers)
            results.append(
                TestFunction(
                    file=_rel(path),
                    name=node.name,
                    lineno=node.lineno,
                    markers=markers,
                    body_hash=body_hash,
                    body_lines=body.count("\n") + 1 if body else 0,
                    classification=classification,
                    tier=tier,
                    notes=notes,
                    is_integration=is_int,
                    is_doc_or_file_only=is_doc,
                )
            )
        # nested class methods
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not node.name.startswith("Test"):
                continue
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not child.name.startswith("test_"):
                    continue
                body = _body_source(child, source) or ""
                markers = []
                for dec in child.decorator_list:
                    dec_src = ast.get_source_segment(source, dec) or ""
                    markers.extend([m for pair in MARKER_RE.findall(dec_src) for m in pair if m])
                body_hash = hashlib.sha256(re.sub(r"\s+", " ", body).strip().encode()).hexdigest()[:16]
                classification, tier, notes, is_int, is_doc = _classify(
                    _rel(path), f"{node.name}.{child.name}", body, markers
                )
                results.append(
                    TestFunction(
                        file=_rel(path),
                        name=f"{node.name}.{child.name}",
                        lineno=child.lineno,
                        markers=sorted(set(markers)),
                        body_hash=body_hash,
                        body_lines=body.count("\n") + 1 if body else 0,
                        classification=classification,
                        tier=tier,
                        notes=notes,
                        is_integration=is_int,
                        is_doc_or_file_only=is_doc,
                    )
                )
    return results


def collect_frontend_tests() -> list[dict]:
    rows: list[dict] = []
    if not FRONTEND_TESTS.exists():
        return rows
    for path in sorted(FRONTEND_TESTS.rglob("*.test.*")):
        text = path.read_text(encoding="utf-8", errors="replace")
        names = re.findall(r"(?:it|test)\(\s*['\"]([^'\"]+)['\"]", text)
        classification = "KEEP_CORE"
        if "allowlist" in path.name or "boundary" in path.name or "v1Client" in path.name:
            classification = "KEEP_CORE"
        elif "featureModules" in path.name:
            classification = "KEEP_CORE"
        rows.append(
            {
                "file": _rel(path),
                "test_count": len(names) or (1 if "describe" in text else 0),
                "names": names,
                "classification": classification,
                "tier": "1" if any(k in path.name for k in ("v1Client", "allowlist", "boundary")) else "2",
            }
        )
    return rows


def docker_inventory() -> dict:
    hits: list[dict] = []
    roots = [
        REPO / "README.md",
        REPO / "docs",
        REPO / "deploy",
        REPO / "scripts",
        REPO / "UI_API" / "tests",
        REPO / ".github",
        REPO / "docs" / "operations",
    ]
    for root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if not path.is_file():
                continue
            if any(part in {".git", "node_modules", ".venv", "__pycache__", "models", "weights"} for part in path.parts):
                continue
            if path.suffix.lower() not in {".md", ".yml", ".yaml", ".py", ".sh", ".txt", ".example", ".json", ""} and path.name not in {
                "Dockerfile.api",
                "Dockerfile.worker",
            }:
                if "Dockerfile" not in path.name and "compose" not in path.name:
                    continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not DOCKER_RE.search(text) and "Dockerfile" not in path.name and "compose" not in path.name.lower():
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if DOCKER_RE.search(line) or "Dockerfile" in line:
                    hits.append({"file": _rel(path), "line": i, "text": line.strip()[:160]})
    artifacts = []
    if DEPLOY_DIR.exists():
        for path in sorted(DEPLOY_DIR.rglob("*")):
            if path.is_file():
                artifacts.append(_rel(path))
    return {"references": hits[:200], "reference_count": len(hits), "deploy_artifacts": artifacts}


def local_process_map() -> dict:
    return {
        "current_entrypoints": [
            "UI_API/main.py — API process",
            "UI_API/backend/scripts/run_worker.py — Worker process",
            "scripts/start_emotion_llama.sh — optional Emotion-LLaMA",
            "scripts/start_r1_omni.sh — optional R1-Omni",
            "scripts/pre_deploy_check.sh / post_deploy_smoke.sh — ops checks",
            "scripts/backup_postgres.sh / restore_postgres.sh — DB ops",
        ],
        "missing_local_orchestration": [
            "scripts/local/setup.sh",
            "scripts/local/start.sh",
            "scripts/local/stop.sh",
            "scripts/local/status.sh",
            "scripts/local/doctor.sh",
            "scripts/local/test_fast.sh",
            "scripts/local/test_full.sh",
        ],
        "runtime_dirs_planned": [
            "runtime/pids",
            "runtime/logs",
            "runtime/object_storage",
            "runtime/tmp",
            "runtime/state",
        ],
        "docker_primary": False,
        "note": "Primary runtime is native local/LAN processes; Docker is not required.",
    }


def build_inventory() -> dict:
    backend = collect_python_tests(BACKEND_TESTS)
    frontend = collect_frontend_tests()
    by_class = Counter(t.classification for t in backend)
    by_tier = Counter(t.tier for t in backend)
    by_file = Counter(t.file for t in backend)
    name_counts = Counter(t.name for t in backend)
    duplicate_names = sorted([n for n, c in name_counts.items() if c > 1])
    hash_groups: dict[str, list[str]] = defaultdict(list)
    for t in backend:
        if t.body_hash:
            hash_groups[t.body_hash].append(f"{t.file}::{t.name}")
    similar_bodies = {h: names for h, names in hash_groups.items() if len(names) > 1}
    # reduce noise: only report groups with body_lines >= 5
    similar_report = []
    hash_to_lines = {t.body_hash: t.body_lines for t in backend}
    for h, names in sorted(similar_bodies.items(), key=lambda x: -len(x[1])):
        if hash_to_lines.get(h, 0) >= 5:
            similar_report.append({"body_hash": h, "count": len(names), "tests": names[:12]})
    modules = sorted({Path(t.file).name for t in backend})
    markers = sorted({m for t in backend for m in t.markers})
    tdd_files = sorted(_rel(p) for p in TDD_DIR.glob("*.md")) if TDD_DIR.exists() else []
    return {
        "backend": {
            "file_count": len(by_file),
            "function_count": len(backend),
            "by_classification": dict(by_class),
            "by_tier": dict(by_tier),
            "markers_found": markers,
            "modules": modules,
            "duplicate_names": duplicate_names[:50],
            "similar_body_groups": similar_report[:40],
            "functions": [asdict(t) for t in backend],
        },
        "frontend": {
            "file_count": len(frontend),
            "test_count": sum(int(r["test_count"]) for r in frontend),
            "files": frontend,
        },
        "tdd_evidence_files": tdd_files,
        "docker": docker_inventory(),
        "local_process_map": local_process_map(),
    }


def to_markdown(data: dict) -> str:
    b = data["backend"]
    lines = [
        "# Test Inventory",
        "",
        f"- Backend test files: **{b['file_count']}**",
        f"- Backend test functions: **{b['function_count']}**",
        f"- Frontend test files: **{data['frontend']['file_count']}**",
        f"- Frontend test cases (approx): **{data['frontend']['test_count']}**",
        f"- TDD evidence docs: **{len(data['tdd_evidence_files'])}**",
        "",
        "## Classification (backend functions)",
        "",
        "| Class | Count |",
        "| --- | ---: |",
    ]
    for k, v in sorted(b["by_classification"].items()):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Estimated tier",
        "",
        "| Tier | Count |",
        "| --- | ---: |",
    ]
    for k, v in sorted(b["by_tier"].items()):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        f"Duplicate test names: {len(b['duplicate_names'])}",
        f"Similar-body groups (body ≥5 lines): {len(b['similar_body_groups'])}",
        f"Docker references scanned: {data['docker']['reference_count']}",
        f"Deploy artifacts: {len(data['docker']['deploy_artifacts'])}",
        "",
        "## Notes",
        "",
        "- Classifications are inventory heuristics for L0; L4 performs actual removal/merge with TEST_REMOVAL_LOG.",
        "- KEEP_CORE / KEEP_INTEGRATION are protected from blind deletion.",
        "- Docker is inventoried for L1 relocation/archive; not required for local runtime.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project_2026 test/runtime inventory")
    parser.add_argument("--json", type=Path, help="Write full JSON inventory")
    parser.add_argument("--md", type=Path, help="Write markdown summary")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    data = build_inventory()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(to_markdown(data), encoding="utf-8")
    if not args.quiet:
        print(to_markdown(data))
        print(
            json.dumps(
                {
                    "backend_functions": data["backend"]["function_count"],
                    "backend_files": data["backend"]["file_count"],
                    "frontend_files": data["frontend"]["file_count"],
                    "classifications": data["backend"]["by_classification"],
                    "docker_refs": data["docker"]["reference_count"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
