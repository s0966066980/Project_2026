#!/usr/bin/env python3
"""Run a bounded reliable worker cycle outside the API process."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
UI_API_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(UI_API_DIR) not in sys.path:
    sys.path.insert(0, str(UI_API_DIR))


def _bootstrap_production_worker() -> None:
    from services.outbox_delivery_router import configure_default_outbox_router
    from services.worker_handler_registry import default_registry
    from services.worker_handlers import register_production_handlers

    register_production_handlers()
    configure_default_outbox_router()
    default_registry().validate_required_handlers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project_2026 reliable background worker")
    parser.add_argument("--once", action="store_true", help="Process one bounded cycle and exit")
    parser.add_argument("--max-jobs", type=int, default=20)
    parser.add_argument("--max-outbox", type=int, default=50)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--worker-id", default="")
    args = parser.parse_args(argv)

    from repositories import postgres_utils
    from services import observability_service, worker_service

    observability_service.configure_logging()
    worker_id = str(args.worker_id or os.environ.get("WORKER_ID") or f"worker-{uuid4().hex[:8]}")
    _bootstrap_production_worker()

    if postgres_utils.storage_backend() == "postgres":
        from repositories.postgres_worker_store import PostgresJobStore

        store = PostgresJobStore()

        def cycle() -> dict[str, int]:
            return worker_service.run_worker_cycle(
                store=store,
                worker_id=worker_id,
                max_jobs=args.max_jobs,
                max_outbox=args.max_outbox,
            )
    else:

        def cycle() -> dict[str, int]:
            return worker_service.run_worker_cycle(
                worker_id=worker_id,
                max_jobs=args.max_jobs,
                max_outbox=args.max_outbox,
            )

    if args.once:
        summary = cycle()
        print(
            f"worker_id={worker_id} jobs={summary['jobs_processed']} outbox={summary['outbox_processed']}",
            flush=True,
        )
        return 0

    while True:
        summary = cycle()
        if summary["jobs_processed"] == 0 and summary["outbox_processed"] == 0:
            time.sleep(max(0.2, float(args.poll_seconds)))
        else:
            print(
                f"worker_id={worker_id} jobs={summary['jobs_processed']} outbox={summary['outbox_processed']}",
                flush=True,
            )


if __name__ == "__main__":
    raise SystemExit(main())
