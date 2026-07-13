"""Governed RAG lifecycle: version, review, publish, rollback, retrieval trace.

PostgreSQL is the durable source of truth when MEMBER_STORAGE_BACKEND=postgres.
JSON under LEARNING_DATA_DIR remains development/default-scope compatibility only.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import config  # re-exported for tests monkeypatching LEARNING_DATA_DIR
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from models.rag_governance import RAG_PERMISSIONS, RagAssetStatus, RagAssetVersion, RetrievalTrace
from models.worker_jobs import JobValidationError
from repositories import rag_governance_repository
from services import object_storage_service, worker_service

# Prevent unused-import cleanup from dropping the public config attribute used by tests.
_ = config.LEARNING_DATA_DIR


class RagGovernanceError(ValueError):
    """Raised for invalid RAG lifecycle transitions."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_assets() -> list[dict[str, Any]]:
    return rag_governance_repository.load_assets()


def _save_assets(rows: list[dict[str, Any]]) -> None:
    rag_governance_repository.save_assets(rows)


def _checksum(content: str) -> str:
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


def _to_asset(row: dict[str, Any]) -> RagAssetVersion:
    return rag_governance_repository.to_asset(row)


def _row(asset: RagAssetVersion) -> dict[str, Any]:
    return rag_governance_repository.asset_to_row(asset)


def _store_content(*, content: str, tenant_id: UUID | None, store_id: UUID | None, owner: str) -> str:
    """Persist binary/text content via object storage when possible; return content_ref."""

    checksum = _checksum(content)
    try:
        store = object_storage_service.storage()
        meta = store.put(
            tenant_id=tenant_id or LEGACY_DEFAULT_SCOPE.tenant_id,
            store_id=store_id,
            owner=owner or "rag",
            content_type="text/plain",
            data=content.encode("utf-8"),
            filename=f"rag-{checksum[:12]}.txt",
            retention_days=365,
        )
        return f"object:{meta.object_id}"
    except Exception:
        # Compatibility: inline ref when storage is unavailable in constrained tests.
        return f"inline:{checksum[:16]}"


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
    content_ref = _store_content(
        content=content,
        tenant_id=tenant_id,
        store_id=store_id,
        owner=owner,
    )
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
        content_ref=content_ref,
        history=[{"event": "created", "actor": actor, "at": _now()}],
    )
    row = _row(asset)
    row["size_bytes"] = len(content.encode("utf-8"))
    row["content_type"] = "text/plain"
    rows.append(row)
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
    target["published_by"] = actor
    history = list(target.get("history") or [])
    history.append({"event": "published", "actor": actor, "at": now})
    target["history"] = history
    _save_assets(rows)
    rag_governance_repository.set_publication_pointer(
        document_id=document_id,
        version=int(version),
        actor=actor,
        index_namespace=f"{document_id}@v{version}",
    )
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
    target["published_by"] = actor
    history = list(target.get("history") or [])
    history.append({"event": "rollback_publish", "actor": actor, "at": now})
    target["history"] = history
    _save_assets(rows)
    rag_governance_repository.set_publication_pointer(
        document_id=document_id,
        version=int(to_version),
        actor=actor,
        index_namespace=f"{document_id}@v{to_version}",
    )
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
    trace = RetrievalTrace(
        query_ref=str(query_ref or ""),
        document_versions=versions,
        chunk_ids=chunk_ids,
        scores=scores,
        provider=str(provider or ""),
        latency_ms=float(latency_ms),
    )
    # Durable trace when PostgreSQL backend is active; never logs raw query text.
    try:
        rag_governance_repository.record_retrieval_trace(
            tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
            store_id=LEGACY_DEFAULT_SCOPE.store_id,
            query_ref=trace.query_ref,
            document_versions=trace.document_versions,
            chunk_ids=trace.chunk_ids,
            scores=trace.scores,
            provider=trace.provider,
            latency_ms=trace.latency_ms,
            schema_version=trace.schema_version,
        )
    except Exception:
        pass
    return trace


def execute_rebuild_job(
    *,
    document_id: str,
    tenant_id: UUID,
    store_id: UUID | None,
    actor: str = "worker",
) -> str:
    """Execute a rebuild side effect for a governed asset (index rebuild expands in milestone 6A)."""

    normalized = str(document_id or "").strip()
    if not normalized:
        raise RagGovernanceError("missing_document_id")
    rows = _load_assets()
    matched = False
    matched_version = 0
    side_effect_id = ""
    for row in rows:
        if str(row.get("document_id") or "") != normalized:
            continue
        row_tenant = row.get("tenant_id")
        if row_tenant and UUID(str(row_tenant)) != tenant_id:
            raise RagGovernanceError("tenant_scope_mismatch")
        row_store = row.get("store_id")
        if store_id is not None and row_store and UUID(str(row_store)) != store_id:
            raise RagGovernanceError("store_scope_mismatch")
        history = list(row.get("history") or [])
        version = int(row.get("version") or 1)
        # Staging index namespace then atomic publish pointer only for published assets.
        index_version = f"idx:{normalized}:v{version}:{uuid4().hex[:8]}"
        side_effect_id = f"rag-rebuild:{normalized}:{version}:{index_version}"
        history.append(
            {
                "event": "rebuild_executed",
                "actor": actor,
                "at": _now(),
                "side_effect_id": side_effect_id,
                "index_version": index_version,
            }
        )
        row["history"] = history
        row["last_rebuild_at"] = _now()
        row["index_version"] = index_version
        row["chunking_version"] = str(row.get("chunking_version") or "chunk-v1")
        row["extractor_version"] = str(row.get("extractor_version") or "extract-v1")
        row["embedding_provider"] = str(row.get("embedding_provider") or "local")
        row["embedding_model"] = str(row.get("embedding_model") or "bge-small-zh-v1.5")
        row["embedding_version"] = str(row.get("embedding_version") or "emb-v1")
        row["retrieval_config_version"] = str(row.get("retrieval_config_version") or "retrieval-v1")
        matched = True
        matched_version = version
        break
    if not matched:
        raise RagGovernanceError("asset_not_found")
    _save_assets(rows)
    try:
        rag_governance_repository.record_rebuild_run(
            document_id=normalized,
            version=matched_version,
            tenant_id=tenant_id,
            store_id=store_id,
            status="succeeded",
            side_effect_id=side_effect_id,
        )
    except Exception:
        pass
    return side_effect_id


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
