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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project_2026 reliable background worker")
    parser.add_argument("--once", action="store_true", help="Process one bounded cycle and exit")
    parser.add_argument("--max-jobs", type=int, default=20)
    parser.add_argument("--max-outbox", type=int, default=50)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--worker-id", default="")
    args = parser.parse_args(argv)

    # Prefer PostgreSQL job tables when commercial storage is postgres.
    from repositories import postgres_utils
    from services import observability_service, worker_service

    observability_service.configure_logging()
    worker_id = str(args.worker_id or os.environ.get("WORKER_ID") or f"worker-{uuid4().hex[:8]}")

    if postgres_utils.storage_backend() == "postgres":
        from repositories import worker_job_repository
        from services.worker_service import JobHandlerResult

        def process_postgres_cycle() -> dict[str, int]:
            jobs = 0
            outbox = 0
            for _ in range(max(0, args.max_jobs)):
                job = worker_job_repository.claim_next_job(worker_id=worker_id)
                if job is None:
                    break
                # Default handlers succeed; specialized adapters register later.
                result = JobHandlerResult(success=True, retryable=False, safe_error="")
                if result.success:
                    worker_job_repository.complete_job(job.job_id)
                    observability_service.increment_metric("worker_jobs_success_total")
                jobs += 1
            for _ in range(max(0, args.max_outbox)):
                event = worker_job_repository.claim_next_outbox(worker_id=worker_id)
                if event is None:
                    break
                worker_job_repository.mark_outbox_published(event["id"])
                observability_service.increment_metric("worker_jobs_success_total", status="outbox")
                outbox += 1
            metrics = worker_job_repository.queue_metrics()
            observability_service.set_metric("worker_jobs_depth", metrics.depth)
            observability_service.set_metric("worker_jobs_oldest_age_seconds", metrics.oldest_age_seconds)
            observability_service.set_metric("order_outbox_pending", metrics.pending_outbox)
            observability_service.set_metric("queue_backlog", metrics.depth + metrics.pending_outbox)
            return {"jobs_processed": jobs, "outbox_processed": outbox}

        cycle = process_postgres_cycle
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
