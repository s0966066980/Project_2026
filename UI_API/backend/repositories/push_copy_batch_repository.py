"""Progress records for one-click push copy generation.

The batch table exists so progress survives a restart: the browser tab that started the run is
not the owner of the work, and background_jobs alone cannot say how many items are done.
"""

import json
import os
from uuid import uuid4

import config
from models.commercial_scope import CommercialScope, is_legacy_store_scope
from repositories import postgres_utils

BATCHES_PATH = os.path.join(config.LEARNING_DATA_DIR, "push_copy_batches.json")

MODES = ("fill_missing", "regenerate")
TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")


def _text(value) -> str:
    return str(value or "").strip()


def _row(record: dict) -> dict:
    total = int(record.get("total") or 0)
    succeeded = int(record.get("succeeded") or 0)
    failed = int(record.get("failed") or 0)
    processed = succeeded + failed
    return {
        "batch_id": _text(record.get("batch_id")),
        "mode": _text(record.get("mode")) or "fill_missing",
        "item_ids": list(record.get("item_ids") or []),
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "processed": processed,
        "percent": int(processed * 100 / total) if total else 0,
        "status": _text(record.get("status")) or "pending",
        "last_error": _text(record.get("last_error")),
        "created_at": _text(record.get("created_at")),
        "updated_at": _text(record.get("updated_at")),
    }


def _json_all() -> list[dict]:
    if not os.path.exists(BATCHES_PATH):
        return []
    try:
        with open(BATCHES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _json_save(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(BATCHES_PATH), exist_ok=True)
    tmp = f"{BATCHES_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows[-50:], f, ensure_ascii=False, indent=2)
    os.replace(tmp, BATCHES_PATH)


def create_batch(
    scope: CommercialScope,
    *,
    mode: str,
    item_ids: list[str],
    actor_id: str = "",
) -> dict:
    normalized_mode = mode if mode in MODES else "fill_missing"
    ids = [_text(value) for value in item_ids if _text(value)]
    batch_id = f"pcb_{uuid4().hex}"
    if postgres_utils.use_postgres():
        from psycopg.types.json import Jsonb

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO push_copy_batches (
                    batch_id, tenant_id, store_id, mode, item_ids, total, status, actor_id
                ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
                RETURNING batch_id, mode, item_ids, total, succeeded, failed, status,
                          last_error, created_at, updated_at
                """,
                (batch_id, scope.tenant_id, scope.store_id, normalized_mode, Jsonb(ids), len(ids), _text(actor_id)),
            )
            record = dict(cur.fetchone())
            conn.commit()
        record["created_at"] = str(record.get("created_at") or "")
        record["updated_at"] = str(record.get("updated_at") or "")
        return _row(record)
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON batch storage only supports the legacy Default Scope")
    rows = _json_all()
    record = {
        "batch_id": batch_id, "mode": normalized_mode, "item_ids": ids,
        "total": len(ids), "succeeded": 0, "failed": 0, "status": "pending",
        "last_error": "", "actor_id": _text(actor_id), "created_at": "", "updated_at": "",
    }
    rows.append(record)
    _json_save(rows)
    return _row(record)


def get_batch(scope: CommercialScope, batch_id: str) -> dict | None:
    key = _text(batch_id)
    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT batch_id, mode, item_ids, total, succeeded, failed, status,
                       last_error, created_at, updated_at
                FROM push_copy_batches
                WHERE tenant_id = %s AND store_id = %s AND batch_id = %s
                """,
                (scope.tenant_id, scope.store_id, key),
            )
            record = cur.fetchone()
        return _row(dict(record)) if record else None
    return next((_row(row) for row in _json_all() if _text(row.get("batch_id")) == key), None)


def latest_batch(scope: CommercialScope) -> dict | None:
    """Most recent batch for the scope, so the page can resume showing progress after a reload."""

    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT batch_id, mode, item_ids, total, succeeded, failed, status,
                       last_error, created_at, updated_at
                FROM push_copy_batches
                WHERE tenant_id = %s AND store_id = %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (scope.tenant_id, scope.store_id),
            )
            record = cur.fetchone()
        return _row(dict(record)) if record else None
    rows = _json_all()
    return _row(rows[-1]) if rows else None


def mark_running(scope: CommercialScope, batch_id: str) -> None:
    _update(scope, batch_id, "status = 'running', updated_at = NOW()", (), json_patch={"status": "running"})


def record_item_result(scope: CommercialScope, batch_id: str, *, ok: bool, error: str = "") -> None:
    """Count one item. Called after each LLM call so progress advances while the batch runs."""

    if ok:
        _update(scope, batch_id, "succeeded = succeeded + 1, updated_at = NOW()", (), json_inc="succeeded")
    else:
        _update(
            scope, batch_id,
            "failed = failed + 1, last_error = %s, updated_at = NOW()",
            (_text(error)[:500],),
            json_inc="failed", json_patch={"last_error": _text(error)[:500]},
        )


def finish_batch(scope: CommercialScope, batch_id: str, *, status: str) -> None:
    final = status if status in TERMINAL_STATUSES else "succeeded"
    _update(scope, batch_id, "status = %s, updated_at = NOW()", (final,), json_patch={"status": final})


def _update(
    scope: CommercialScope,
    batch_id: str,
    assignment: str,
    params: tuple,
    *,
    json_inc: str = "",
    json_patch: dict | None = None,
) -> None:
    key = _text(batch_id)
    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE push_copy_batches SET {assignment} WHERE tenant_id = %s AND store_id = %s AND batch_id = %s",
                (*params, scope.tenant_id, scope.store_id, key),
            )
            conn.commit()
        return
    rows = _json_all()
    for row in rows:
        if _text(row.get("batch_id")) == key:
            if json_inc:
                row[json_inc] = int(row.get(json_inc) or 0) + 1
            for field, value in (json_patch or {}).items():
                row[field] = value
    _json_save(rows)
