"""Explicit Runtime Persistence Profile operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from modules.runtime_persistence.evidence import inspect_persistence, run_write_probe  # noqa: E402
from modules.runtime_persistence.migrations import migrate_to_head  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "migrate", "write-probe"))
    args = parser.parse_args()
    if args.command == "status":
        result = inspect_persistence()
    elif args.command == "migrate":
        result = migrate_to_head().as_dict()
    else:
        result = run_write_probe()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
