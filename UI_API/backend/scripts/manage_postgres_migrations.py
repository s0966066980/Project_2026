"""Inspect, validate, and apply the versioned PostgreSQL migrations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

# The script must add backend/ before importing the repository package.
from repositories import postgres_utils  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Project_2026 PostgreSQL schema migrations.")
    parser.add_argument("command", choices=("status", "validate", "apply"))
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Fail when valid local migrations have not been applied.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "apply":
            plan = postgres_utils.apply_migrations()
        else:
            plan = postgres_utils.get_migration_plan()
            if args.command == "status":
                print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
            postgres_utils.validate_migration_plan(
                plan,
                require_clean=bool(args.require_clean),
            )
        if args.command != "status":
            print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
        return 0
    except postgres_utils.PostgresUnavailableError as exc:
        print(f"PostgreSQL migration command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
