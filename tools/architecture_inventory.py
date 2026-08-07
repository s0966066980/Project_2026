#!/usr/bin/env python3
"""Generate the backend current-state architecture inventory.

This is a *descriptive* generator. It records what the code does today; it does
not rank, judge, or recommend. Re-run it and diff ``inventory.json`` to see what
actually changed.

Outputs
-------
docs/architecture/inventory.json
    Source of truth. One fact per line-ish; diff this.
docs/architecture/index.html
    Self-contained viewer that embeds the JSON above.

Usage
-----
    python3 tools/architecture_inventory.py

Sections implemented so far:
    * tables  -- table ownership by writing file, with app/worker attribution
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "UI_API" / "backend"
MIGRATIONS = BACKEND / "schemas" / "migrations"
OUTPUT_DIR = REPO_ROOT / "docs" / "architecture"

# Entry points that define which process a module executes in.
ENTRY_POINTS = {
    "app": REPO_ROOT / "UI_API" / "main.py",
    "worker": BACKEND / "scripts" / "run_worker.py",
}

# Words that follow a write keyword but are not table names.
SQL_NOISE = {
    "set", "from", "where", "and", "or", "select", "values", "returning",
    "on", "conflict", "as", "only", "table", "into",
    "excluded",  # ON CONFLICT pseudo-table
    "skip", "locked", "nowait", "share",  # FOR UPDATE SKIP LOCKED
    "lateral", "unnest", "generate_series",
}


# --------------------------------------------------------------------------
# import graph / process attribution
# --------------------------------------------------------------------------

def _module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


# Both entry points prepend UI_API/backend to sys.path, so ``services.x`` and
# ``backend.services.x`` are the same module. Index under both roots.
IMPORT_ROOTS = (REPO_ROOT / "UI_API", BACKEND)


def build_module_index() -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in (REPO_ROOT / "UI_API").rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        for root in IMPORT_ROOTS:
            if path.is_relative_to(root):
                name = _module_name(path, root)
                if name:
                    index.setdefault(name, path)
    return index


def imports_of(path: Path, index: dict[str, Path]) -> set[Path]:
    """Resolve the local modules a file imports, ignoring third-party ones."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()

    root = BACKEND if path.is_relative_to(BACKEND) else REPO_ROOT / "UI_API"
    own = _module_name(path, root)
    # For a package's __init__.py the module name *is* the package name, so
    # ``from .x import y`` must not strip a level.
    if path.name == "__init__.py":
        package = own
    else:
        package = own.rsplit(".", 1)[0] if "." in own else ""
    targets: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - node.level + 1]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            if not prefix:
                continue
            targets.add(prefix)
            targets.update(f"{prefix}.{alias.name}" for alias in node.names)

    # bootstrap/module_registry.py imports capability routers by string through
    # __import__(), which a plain Import/ImportFrom walk cannot see.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        dynamic = (
            (isinstance(func, ast.Name) and func.id == "__import__")
            or (isinstance(func, ast.Attribute) and func.attr == "import_module")
        )
        if not dynamic:
            continue
        for arg in node.args[:1]:
            for const in ast.walk(arg):
                if isinstance(const, ast.Constant) and isinstance(const.value, str):
                    targets.add(const.value)
        # The dotted names are often held in a nearby tuple of literals.
        for sibling in ast.walk(tree):
            if isinstance(sibling, (ast.Tuple, ast.List)):
                for element in sibling.elts:
                    if (
                        isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                        and element.value in index
                    ):
                        targets.add(element.value)

    return {index[t] for t in targets if t in index}


def inheritance_edges(index: dict[str, Path]) -> dict[Path, set[Path]]:
    """Map each file to the files whose classes it subclasses.

    ``PostgresCartStore(SQLiteCartStore)`` inherits every SQL literal from the
    SQLite module and runs it against PostgreSQL, so the statement's engine
    cannot be read off the file that spells it out.
    """
    edges: dict[Path, set[Path]] = defaultdict(set)
    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        sources = imports_of(path, index)
        bases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.add(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.add(base.attr)
        if not bases:
            continue
        for source in sources:
            try:
                text = source.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if any(re.search(rf"^class\s+{re.escape(b)}\b", text, re.M) for b in bases):
                edges[source].add(path)
    return edges


def reachable_from(entry: Path, index: dict[str, Path]) -> set[Path]:
    seen: set[Path] = set()
    queue = [entry]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(imports_of(current, index) - seen)
    return seen


def process_attribution(index: dict[str, Path]) -> dict[Path, list[str]]:
    """Map each file to the processes whose import closure contains it."""
    attribution: dict[Path, set[str]] = defaultdict(set)
    for process, entry in ENTRY_POINTS.items():
        if not entry.exists():
            continue
        for path in reachable_from(entry, index):
            attribution[path].add(process)
    return {path: sorted(procs) for path, procs in attribution.items()}


# --------------------------------------------------------------------------
# SQL scanning
# --------------------------------------------------------------------------

WRITE_RE = re.compile(
    r"(?<!FOR )\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
    r"(\{[^}]*\}|\"?[a-zA-Z_][a-zA-Z0-9_]*\"?|%s)",
    re.IGNORECASE,
)
READ_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:public\.)?(\"?[a-zA-Z_][a-zA-Z0-9_]*\"?)",
    re.IGNORECASE,
)
CREATE_RE = re.compile(
    r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:public\.)?\"?([a-zA-Z_][a-zA-Z0-9_]*)\"?",
    re.IGNORECASE,
)
# Common table expressions are query-local names, not tables.
CTE_RE = re.compile(r"(?:WITH|,)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", re.IGNORECASE)

# A statement only counts as SQL if the literal actually looks like SQL. "WITH"
# is deliberately absent: English prose uses it constantly, and a CTE is always
# followed by one of the verbs below anyway.
SQL_HINT_RE = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|CREATE\s+TABLE)\b", re.IGNORECASE
)


def _normalise(token: str) -> tuple[str | None, bool]:
    """Return (table_name, is_dynamic)."""
    token = token.strip().strip('"')
    if token.startswith("{") or token == "%s":
        return None, True
    if not token or token.lower() in SQL_NOISE:
        return None, False
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", token):
        return None, False
    return token.lower(), False


def sql_literals(source: str) -> list[tuple[str, int]]:
    """Extract string literals that look like SQL, with their line numbers.

    Scanning whole files misreads Python (``from x import y``) and English prose
    in comments as SQL, so only string constants are considered. f-strings keep
    their ``{...}`` placeholders so dynamic table names stay visible.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    literals: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    parts.append("{expr}")
            text = "".join(parts)
        else:
            continue
        if SQL_HINT_RE.search(text):
            literals.append((text, getattr(node, "lineno", 0)))
    return literals


@dataclass
class Access:
    writes: dict[str, int] = field(default_factory=dict)
    reads: int = 0


SQLITE_MARKERS = ("sqlite3",)
POSTGRES_MARKERS = ("psycopg", "psycopg2", "asyncpg", "postgres_utils", "postgres_pool")


def detect_engine(path: Path) -> str:
    """Which database engine a file's SQL actually targets.

    Table names alone are ambiguous: ``ordering_carts`` exists both as a
    PostgreSQL table and inside a per-module SQLite store, and they are
    different physical stores.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return "unknown"

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)

    flat = " ".join(names)
    sqlite = any(marker in flat for marker in SQLITE_MARKERS)
    postgres = any(marker in flat for marker in POSTGRES_MARKERS)
    if sqlite and postgres:
        return "both"
    if sqlite:
        return "sqlite"
    if postgres:
        return "postgres"
    return "unknown"


def scan_backend() -> tuple[dict[str, dict[str, Access]], list[dict]]:
    """Return {table: {file: Access}} plus a list of unresolved dynamic writes."""
    table_access: dict[str, dict[str, Access]] = defaultdict(lambda: defaultdict(Access))
    dynamic: list[dict] = []

    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(REPO_ROOT))

        for statement, lineno in sql_literals(source):
            ctes = {name.lower() for name in CTE_RE.findall(statement)}

            for match in WRITE_RE.finditer(statement):
                verb = match.group(1).upper().split()[0]
                table, is_dynamic = _normalise(match.group(2))
                if is_dynamic:
                    dynamic.append({
                        "file": rel,
                        "line": lineno,
                        "verb": verb,
                        "snippet": re.sub(r"\s+", " ", match.group(0))[:80],
                    })
                    continue
                if table is None or table in ctes:
                    continue
                counts = table_access[table][rel].writes
                counts[verb] = counts.get(verb, 0) + 1

            for match in READ_RE.finditer(statement):
                table, _ = _normalise(match.group(1))
                if table is None or table in ctes:
                    continue
                table_access[table][rel].reads += 1

    return table_access, dynamic


def scan_migrations() -> dict[str, str]:
    """Map each created table to the migration file that created it."""
    created: dict[str, str] = {}
    if not MIGRATIONS.exists():
        return created
    for path in sorted(MIGRATIONS.glob("*.sql")):
        for name in CREATE_RE.findall(path.read_text(encoding="utf-8")):
            created.setdefault(name.lower(), path.name)
    return created


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------

def module_of(rel_path: str) -> str:
    parts = Path(rel_path).parts
    try:
        i = parts.index("backend")
    except ValueError:
        return "?"
    tail = parts[i + 1:]
    if len(tail) <= 1:
        return "backend (root)"
    if tail[0] == "modules" and len(tail) > 2:
        return f"modules/{tail[1]}"
    return tail[0]


def build_tables(
    access: dict[str, dict[str, Access]],
    created: dict[str, str],
    attribution: dict[Path, list[str]],
    subclasses: dict[Path, set[Path]],
) -> list[dict]:
    def engines_for(path: Path) -> tuple[list[str], list[str]]:
        """Engines this file's SQL runs on, and who contributes each."""
        found = {detect_engine(path)}
        via = []
        for child in sorted(subclasses.get(path, ())):
            child_engine = detect_engine(child)
            if child_engine not in found:
                via.append(str(child.relative_to(REPO_ROOT)))
            found.add(child_engine)
        found.discard("unknown") if len(found) > 1 else None
        return sorted(found), via

    def processes_for(path: Path) -> list[str]:
        procs = set(attribution.get(path, []))
        for child in subclasses.get(path, ()):
            procs.update(attribution.get(child, []))
        return sorted(procs)

    tables = []
    for name in sorted(set(access) | set(created)):
        files = access.get(name, {})
        writers, readers = [], []
        for rel, entry in sorted(files.items()):
            path = REPO_ROOT / rel
            file_engines, engine_via = engines_for(path)
            record = {
                "file": rel,
                "module": module_of(rel),
                "process": processes_for(path),
                "engine": "+".join(file_engines),
                "engines": file_engines,
                "engine_via_subclass": engine_via,
            }
            if entry.writes:
                writers.append({**record, "ops": dict(sorted(entry.writes.items()))})
            elif entry.reads:
                readers.append({**record, "reads": entry.reads})

        writer_modules = sorted({w["module"] for w in writers})
        engines = sorted({e for w in writers for e in w["engines"]})
        pg_writers = [w for w in writers if w["engines"] != ["sqlite"]]
        pg_modules = sorted({w["module"] for w in pg_writers})

        if name not in created:
            state = "no_ddl"
        elif not pg_writers:
            state = "no_writer"
        elif len(pg_modules) > 1:
            state = "shared"
        else:
            state = "single_owner"

        tables.append({
            "name": name,
            "created_by": created.get(name),
            "writers": writers,
            "readers": readers,
            "writer_modules": writer_modules,
            "engines": engines,
            "processes": sorted({p for w in writers for p in w["process"]}),
            "state": state,
            "dual_engine": "sqlite" in engines and any(e != "sqlite" for e in engines),
        })
    return tables


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def render_html(inventory: dict) -> str:
    payload = json.dumps(inventory, ensure_ascii=False)
    template = (Path(__file__).parent / "architecture_inventory_template.html").read_text(
        encoding="utf-8"
    )
    return template.replace("/*__INVENTORY__*/null", payload)


def main() -> None:
    index = build_module_index()
    attribution = process_attribution(index)
    subclasses = inheritance_edges(index)
    access, dynamic = scan_backend()
    created = scan_migrations()
    tables = build_tables(access, created, attribution, subclasses)

    inventory = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git_commit(),
        "generator": "tools/architecture_inventory.py",
        "scope": {
            "root": "UI_API/backend",
            "method": "static scan (raw SQL string literals, ast import graph)",
            "excluded": ["frontend internals", "docker runtime", "R1-Omni internals", "tools/"],
        },
        "sections": {"tables": "implemented"},
        "process_entry_points": {k: str(v.relative_to(REPO_ROOT)) for k, v in ENTRY_POINTS.items()},
        "tables": tables,
        "unresolved_dynamic_writes": dynamic,
        "totals": {
            "tables_total": len(tables),
            "tables_with_writers": sum(1 for t in tables if t["writers"]),
            "tables_shared_by_modules": sum(1 for t in tables if t["state"] == "shared"),
            "tables_without_ddl": sum(1 for t in tables if t["state"] == "no_ddl"),
            "tables_without_writer": sum(1 for t in tables if t["state"] == "no_writer"),
            "tables_dual_engine": sum(1 for t in tables if t["dual_engine"]),
            "tables_sqlite_only": sum(
                1 for t in tables if t["engines"] == ["sqlite"]
            ),
            "migrations": len(list(MIGRATIONS.glob("*.sql"))) if MIGRATIONS.exists() else 0,
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "index.html").write_text(render_html(inventory), encoding="utf-8")
    print(json.dumps(inventory["totals"], indent=2))
    print(f"unresolved dynamic writes: {len(dynamic)}")


if __name__ == "__main__":
    main()
