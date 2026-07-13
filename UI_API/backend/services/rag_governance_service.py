"""Governed RAG lifecycle: version, review, publish, rollback, retrieval trace."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import config
from models.rag_governance import RAG_PERMISSIONS, RagAssetStatus, RagAssetVersion, RetrievalTrace
from models.worker_jobs import JobValidationError
from services import worker_service


class RagGovernanceError(ValueError):
    """Raised for invalid RAG lifecycle transitions."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "rag_asset_versions.json"


def _load_assets() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data if isinstance(data, list) else data.get("assets", [])
    return [dict(row) for row in rows if isinstance(row, dict)]


def _save_assets(rows: list[dict[str, Any]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _checksum(content: str) -> str:
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


def _to_asset(row: dict[str, Any]) -> RagAssetVersion:
    return RagAssetVersion(
        document_id=str(row.get("document_id") or ""),
        version=int(row.get("version") or 1),
        status=RagAssetStatus(str(row.get("status") or RagAssetStatus.DRAFT.value)),
        source=str(row.get("source") or ""),
        checksum=str(row.get("checksum") or ""),
        owner=str(row.get("owner") or ""),
        tenant_id=UUID(row["tenant_id"]) if row.get("tenant_id") else None,
        store_id=UUID(row["store_id"]) if row.get("store_id") else None,
        created_at=str(row.get("created_at") or ""),
        reviewed_at=str(row.get("reviewed_at") or ""),
        published_at=str(row.get("published_at") or ""),
        superseded_at=str(row.get("superseded_at") or ""),
        content_ref=str(row.get("content_ref") or ""),
        history=list(row.get("history") or []),
    )


def _row(asset: RagAssetVersion) -> dict[str, Any]:
    return {
        "document_id": asset.document_id,
        "version": asset.version,
        "status": asset.status.value,
        "source": asset.source,
        "checksum": asset.checksum,
        "owner": asset.owner,
        "tenant_id": str(asset.tenant_id) if asset.tenant_id else None,
        "store_id": str(asset.store_id) if asset.store_id else None,
        "created_at": asset.created_at,
        "reviewed_at": asset.reviewed_at,
        "published_at": asset.published_at,
        "superseded_at": asset.superseded_at,
        "content_ref": asset.content_ref,
        "history": list(asset.history),
    }


def require_rag_permission(permission: str, granted: set[str] | frozenset[str]) -> None:
    if permission not in RAG_PERMISSIONS:
        raise RagGovernanceError(f"Unknown RAG permission: {permission}")
    if permission not in granted:
        raise RagGovernanceError(f"Missing permission: {permission}")


def create_draft(
    *,
    document_id: str,
    content: str,
    source: str,
    owner: str,
    tenant_id: UUID | None = None,
    store_id: UUID | None = None,
    actor: str = "system",
) -> RagAssetVersion:
    rows = _load_assets()
    doc_id = str(document_id or "").strip() or f"doc-{uuid4().hex[:12]}"
    checksum = _checksum(content)
    if any(row.get("checksum") == checksum and row.get("document_id") == doc_id for row in rows):
        raise RagGovernanceError("duplicate_checksum_for_document")
    existing_versions = [int(r.get("version") or 0) for r in rows if r.get("document_id") == doc_id]
    version = max(existing_versions, default=0) + 1
    asset = RagAssetVersion(
        document_id=doc_id,
        version=version,
        status=RagAssetStatus.DRAFT,
        source=source,
        checksum=checksum,
        owner=owner,
        tenant_id=tenant_id,
        store_id=store_id,
        created_at=_now(),
        content_ref=f"inline:{checksum[:16]}",
        history=[{"event": "created", "actor": actor, "at": _now()}],
    )
    rows.append(_row(asset))
    _save_assets(rows)
    return asset


def submit_for_review(document_id: str, version: int, *, actor: str = "system") -> RagAssetVersion:
    return _transition(document_id, version, RagAssetStatus.REVIEW, actor=actor, event="submitted")


def publish(document_id: str, version: int, *, actor: str = "system") -> RagAssetVersion:
    rows = _load_assets()
    target = None
    for row in rows:
        if row.get("document_id") == document_id and int(row.get("version") or 0) == int(version):
            target = row
            break
    if target is None:
        raise RagGovernanceError("asset_not_found")
    if target.get("status") not in {RagAssetStatus.REVIEW.value, RagAssetStatus.DRAFT.value}:
        raise RagGovernanceError("invalid_publish_status")
    # Supersede previously published versions for the same document.
    now = _now()
    for row in rows:
        if (
            row.get("document_id") == document_id
            and row.get("status") == RagAssetStatus.PUBLISHED.value
            and int(row.get("version") or 0) != int(version)
        ):
            row["status"] = RagAssetStatus.RETIRED.value
            row["superseded_at"] = now
            history = list(row.get("history") or [])
            history.append({"event": "superseded", "actor": actor, "at": now})
            row["history"] = history
    target["status"] = RagAssetStatus.PUBLISHED.value
    target["published_at"] = now
    history = list(target.get("history") or [])
    history.append({"event": "published", "actor": actor, "at": now})
    target["history"] = history
    _save_assets(rows)
    return _to_asset(target)


def rollback(document_id: str, to_version: int, *, actor: str = "system") -> RagAssetVersion:
    rows = _load_assets()
    target = None
    for row in rows:
        if row.get("document_id") == document_id and int(row.get("version") or 0) == int(to_version):
            target = row
            break
    if target is None:
        raise RagGovernanceError("rollback_target_not_found")
    # Only previously published or retired versions may be restored.
    if target.get("status") not in {
        RagAssetStatus.PUBLISHED.value,
        RagAssetStatus.RETIRED.value,
    }:
        raise RagGovernanceError("rollback_target_not_published_history")
    now = _now()
    for row in rows:
        if row.get("document_id") == document_id and row.get("status") == RagAssetStatus.PUBLISHED.value:
            row["status"] = RagAssetStatus.RETIRED.value
            row["superseded_at"] = now
            history = list(row.get("history") or [])
            history.append({"event": "retired_for_rollback", "actor": actor, "at": now})
            row["history"] = history
    target["status"] = RagAssetStatus.PUBLISHED.value
    target["published_at"] = now
    target["superseded_at"] = ""
    history = list(target.get("history") or [])
    history.append({"event": "rollback_publish", "actor": actor, "at": now})
    target["history"] = history
    _save_assets(rows)
    return _to_asset(target)


def list_published(document_id: str | None = None) -> list[RagAssetVersion]:
    rows = _load_assets()
    assets = [_to_asset(row) for row in rows if row.get("status") == RagAssetStatus.PUBLISHED.value]
    if document_id:
        assets = [asset for asset in assets if asset.document_id == document_id]
    return assets


def published_only_retrieval_candidates(document_id: str | None = None) -> list[str]:
    return [f"{asset.document_id}@v{asset.version}" for asset in list_published(document_id)]


def build_retrieval_trace(
    *,
    query_ref: str,
    hits: list[dict[str, Any]],
    provider: str,
    latency_ms: float,
) -> RetrievalTrace:
    versions: list[str] = []
    chunk_ids: list[str] = []
    scores: list[float] = []
    for hit in hits:
        doc_id = str(hit.get("document_id") or "")
        version = hit.get("version")
        if doc_id and version is not None:
            versions.append(f"{doc_id}@v{version}")
        chunk_ids.append(str(hit.get("chunk_id") or hit.get("id") or ""))
        try:
            scores.append(float(hit.get("score") or 0.0))
        except (TypeError, ValueError):
            scores.append(0.0)
    return RetrievalTrace(
        query_ref=str(query_ref or ""),
        document_versions=versions,
        chunk_ids=chunk_ids,
        scores=scores,
        provider=str(provider or ""),
        latency_ms=float(latency_ms),
    )


def enqueue_rebuild(
    *,
    tenant_id: UUID,
    store_id: UUID | None,
    document_id: str,
    actor: str = "system",
    store: worker_service.JobStore | None = None,
) -> dict[str, Any]:
    try:
        job = worker_service.enqueue_job(
            tenant_id=tenant_id,
            store_id=store_id,
            job_type="rag.rebuild",
            payload_ref={"document_id": document_id, "actor": actor},
            idempotency_key=f"rag-rebuild-{document_id}",
            store=store,
        )
    except JobValidationError as exc:
        raise RagGovernanceError(str(exc)) from exc
    return worker_service.job_as_public_dict(job)


def _transition(
    document_id: str,
    version: int,
    status: RagAssetStatus,
    *,
    actor: str,
    event: str,
) -> RagAssetVersion:
    rows = _load_assets()
    for row in rows:
        if row.get("document_id") == document_id and int(row.get("version") or 0) == int(version):
            row["status"] = status.value
            if status is RagAssetStatus.REVIEW:
                row["reviewed_at"] = _now()
            history = list(row.get("history") or [])
            history.append({"event": event, "actor": actor, "at": _now()})
            row["history"] = history
            _save_assets(rows)
            return _to_asset(row)
    raise RagGovernanceError("asset_not_found")
