"""將會員與推薦事件 JSON 匯入 PostgreSQL。

預設只做 dry-run：
    python backend/scripts/migrate_member_storage.py

實際匯入：
    MEMBER_STORAGE_BACKEND=postgres DATABASE_URL=postgresql://... \
    python backend/scripts/migrate_member_storage.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from repositories import member_repository, postgres_utils, recommendation_event_repository


def _read_json_list(path: Path) -> list:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception as exc:
        raise RuntimeError(f"Cannot read JSON list from {path}: {exc}") from exc


def build_plan(members_path: Path, recommendation_events_path: Path) -> dict:
    members = _read_json_list(members_path)
    events = _read_json_list(recommendation_events_path)
    completed_orders = 0
    cancelled_orders = 0
    order_items = 0
    for member in members:
        for order in member.get("orders") or []:
            status = str(order.get("order_status") or "completed")
            if status == "completed" and bool(order.get("is_completed", True)):
                completed_orders += 1
            else:
                cancelled_orders += 1
            if isinstance(order.get("cart_items"), list) and order.get("cart_items"):
                order_items += len(order.get("cart_items") or [])
            else:
                order_items += len(set(order.get("cart_ids") or []))
    return {
        "members": len(members),
        "member_orders": completed_orders + cancelled_orders,
        "completed_orders": completed_orders,
        "cancelled_orders": cancelled_orders,
        "member_order_items": order_items,
        "recommendation_events": len(events),
    }


def apply_migration(members_path: Path, recommendation_events_path: Path) -> dict:
    postgres_utils.init_schema()
    members = _read_json_list(members_path)
    events = _read_json_list(recommendation_events_path)
    for member in members:
        if isinstance(member, dict):
            member_repository.upsert_member(member)
    recommendation_event_repository.append_recommendation_events([
        event for event in events if isinstance(event, dict)
    ])
    return build_plan(members_path, recommendation_events_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate membership JSON data to PostgreSQL.")
    parser.add_argument("--apply", action="store_true", help="Write data to PostgreSQL. Default is dry-run.")
    parser.add_argument(
        "--members-path",
        default=str(ROOT_DIR / "learning_data" / "members.json"),
        help="Path to members.json",
    )
    parser.add_argument(
        "--recommendation-events-path",
        default=str(ROOT_DIR / "learning_data" / "recommendation_events.json"),
        help="Path to recommendation_events.json",
    )
    args = parser.parse_args()

    members_path = Path(args.members_path)
    recommendation_events_path = Path(args.recommendation_events_path)
    plan = build_plan(members_path, recommendation_events_path)
    print(json.dumps({"mode": "apply" if args.apply else "dry_run", **plan}, ensure_ascii=False, indent=2))

    if not args.apply:
        return 0
    if postgres_utils.storage_backend() != "postgres":
        print("ERROR: set MEMBER_STORAGE_BACKEND=postgres before --apply", file=sys.stderr)
        return 2
    apply_migration(members_path, recommendation_events_path)
    print("Migration completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
