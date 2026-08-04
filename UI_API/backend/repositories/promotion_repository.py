"""JSON-backed structured promotion repository."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import config
from models.commercial_scope import CommercialScope, is_legacy_store_scope
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope


def _documents_root() -> Path:
    configured = Path(config.RAG_DOCUMENTS_DIR)
    base = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return configured.resolve() if configured.is_absolute() else (base / configured).resolve()


def promotions_root() -> Path:
    return _documents_root() / "promotions"


def promotion_path(promotion_id: str) -> Path:
    return promotions_root() / f"{promotion_id}.json"


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, list):
        return dict(data[0]) if data and isinstance(data[0], dict) else {}
    return dict(data) if isinstance(data, dict) else {}


def load_json_rows(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data if isinstance(data, list) else [data]
    return [row for row in rows if isinstance(row, dict)]


def list_promotions() -> list[dict]:
    return list_promotions_scoped(resolve_commercial_scope())


def list_promotions_scoped(scope: CommercialScope) -> list[dict]:
    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM promotion_records
                WHERE tenant_id = %s AND store_id = %s
                ORDER BY updated_at DESC, promotion_id
                """,
                (scope.tenant_id, scope.store_id),
            )
            return [dict(row["payload"]) for row in cur.fetchall()]
    if not is_legacy_store_scope(scope):
        return []
    root = promotions_root()
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.glob("*.json")):
        for row in load_json_rows(path):
            record = dict(row)
            record["path"] = path.name
            rows.append(record)
    return rows


def find_promotion_path(promotion_id: str, *, is_valid_id) -> Path | None:
    normalized = str(promotion_id or "").strip()
    if not is_valid_id(normalized):
        return None
    direct_path = promotion_path(normalized)
    if direct_path.exists():
        return direct_path
    root = promotions_root()
    if not root.exists():
        return None
    for path in sorted(root.glob("*.json")):
        record = load_json(path)
        if not record:
            continue
        candidates = {
            str(record.get("id") or "").strip(),
            str(record.get("offer_id") or "").strip(),
            str(record.get("source_id") or "").strip(),
            path.stem,
        }
        if normalized in candidates:
            return path
    return None


def get_promotion(promotion_id: str, *, is_valid_id) -> dict | None:
    return get_promotion_scoped(promotion_id, resolve_commercial_scope(), is_valid_id=is_valid_id)


def get_promotion_scoped(
    promotion_id: str,
    scope: CommercialScope,
    *,
    is_valid_id,
) -> dict | None:
    normalized = str(promotion_id or "").strip()
    if not is_valid_id(normalized):
        return None
    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM promotion_records
                WHERE tenant_id = %s AND store_id = %s AND promotion_id = %s
                """,
                (scope.tenant_id, scope.store_id, normalized),
            )
            row = cur.fetchone()
        return dict(row["payload"]) if row else None
    if not is_legacy_store_scope(scope):
        return None
    path = find_promotion_path(promotion_id, is_valid_id=is_valid_id)
    if not path:
        return None
    record = load_json(path)
    if record:
        record["path"] = path.name
    return record or None


def save_promotion_at_path(path: Path, data: dict[str, Any]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".json.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)
    return dict(data)


def save_promotion(promotion_id: str, data: dict[str, Any]) -> dict:
    return save_promotion_scoped(promotion_id, data, resolve_commercial_scope())


def save_promotion_scoped(
    promotion_id: str,
    data: dict[str, Any],
    scope: CommercialScope,
) -> dict:
    record = dict(data)
    if postgres_utils.use_postgres():
        from psycopg.types.json import Jsonb

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO promotion_records (
                    id, tenant_id, store_id, promotion_id, status, payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, store_id, promotion_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                RETURNING promotion_id
                """,
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.store_id,
                    str(promotion_id),
                    str(record.get("status") or "active"),
                    Jsonb(record),
                ),
            )
            conn.commit()
        return record
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON promotion storage only supports the legacy Default Scope")
    return save_promotion_at_path(promotion_path(promotion_id), data)


def delete_promotion(promotion_id: str, *, is_valid_id) -> bool:
    return delete_promotion_scoped(promotion_id, resolve_commercial_scope(), is_valid_id=is_valid_id)


def delete_promotion_scoped(
    promotion_id: str,
    scope: CommercialScope,
    *,
    is_valid_id,
) -> bool:
    normalized = str(promotion_id or "").strip()
    if not is_valid_id(normalized):
        return False
    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM promotion_records
                WHERE tenant_id = %s AND store_id = %s AND promotion_id = %s
                """,
                (scope.tenant_id, scope.store_id, normalized),
            )
            deleted = bool(cur.rowcount > 0)
            conn.commit()
        return deleted
    if not is_legacy_store_scope(scope):
        return False
    path = find_promotion_path(promotion_id, is_valid_id=is_valid_id)
    if not path:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
