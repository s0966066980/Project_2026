"""Idempotent import of legacy rag_asset_versions.json into durable storage.

Count-only report. Never prints document content or PII.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from repositories import rag_governance_repository  # noqa: E402


def _load_legacy(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("assets", [])
    return [dict(row) for row in rows if isinstance(row, dict)]


def import_rows(rows: list[dict[str, Any]], *, dry_run: bool = False) -> dict[str, int]:
    existing = {(r.get("document_id"), int(r.get("version") or 0)) for r in rag_governance_repository.load_assets()}
    inserted = 0
    skipped = 0
    for row in rows:
        key = (row.get("document_id"), int(row.get("version") or 0))
        if key in existing:
            skipped += 1
            continue
        if not dry_run:
            rag_governance_repository.upsert_asset_row(row)
        inserted += 1
        existing.add(key)
    return {"read": len(rows), "inserted": inserted, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import legacy RAG governance JSON")
    parser.add_argument(
        "--path",
        default=str(Path(config.LEARNING_DATA_DIR) / "rag_asset_versions.json"),
        help="Legacy JSON path",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    rows = _load_legacy(Path(args.path))
    report = import_rows(rows, dry_run=bool(args.dry_run))
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
