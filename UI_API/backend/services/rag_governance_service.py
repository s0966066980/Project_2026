"""Governed RAG lifecycle: version, review, publish, rollback, retrieval trace.

PostgreSQL is the durable source of truth when DATABASE_BACKEND=postgresql.
JSON under LEARNING_DATA_DIR remains development/default-scope compatibility only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import config  # re-exported for tests monkeypatching LEARNING_DATA_DIR
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from models.rag_governance import RAG_PERMISSIONS, RagAssetStatus, RagAssetVersion, RetrievalTrace
from repositories import rag_governance_repository
from services import object_storage_service

# Prevent unused-import cleanup from dropping the public config attribute used by tests.
_ = config.LEARNING_DATA_DIR


class RagGovernanceError(ValueError):
    """Raised for invalid RAG lifecycle transitions."""


_SOURCE_FOLDER = {
    "faq": "faq",
    "policy": "store_policy",
    "menu_supplement": "menu",
    "nutrition": "nutrition",
    "customer_service": "customer_service",
    "promotion": "promotion_notes",
    "manual": "manual",
    "store_information": "store_information",
    "menu_information": "menu_information",
    "promotion_information": "promotion_information",
    "other": "other",
}


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


def _document_details(row: dict[str, Any]) -> dict[str, Any]:
    for event in row.get("history") or []:
        if event.get("event") == "created" and isinstance(event.get("document"), dict):
            return dict(event["document"])
    return {}


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
    except Exception as exc:
        raise RagGovernanceError("content_storage_unavailable") from exc


def read_content(asset: RagAssetVersion | dict[str, Any]) -> str:
    row = _row(asset) if isinstance(asset, RagAssetVersion) else asset
    content_ref = str(row.get("content_ref") or "")
    if not content_ref.startswith("object:"):
        raise RagGovernanceError("content_storage_unavailable")
    object_id = content_ref.removeprefix("object:")
    tenant_id = UUID(str(row.get("tenant_id"))) if row.get("tenant_id") else LEGACY_DEFAULT_SCOPE.tenant_id
    try:
        return object_storage_service.storage().get(object_id, tenant_id=tenant_id).decode("utf-8")
    except Exception as exc:
        raise RagGovernanceError("content_read_failed") from exc


def _documents_root() -> Path:
    configured = Path(config.RAG_DOCUMENTS_DIR)
    base = Path(__file__).resolve().parents[2]
    return configured.resolve() if configured.is_absolute() else (base / configured).resolve()


def _slug(value: str, limit: int = 120) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "")).strip("_").lower()
    return text[:limit] or hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:12]


def _materialized_path(row: dict[str, Any]) -> Path:
    details = _document_details(row)
    source_id = str(details.get("source_id") or row.get("document_id") or "")
    source_type = str(details.get("source_type") or row.get("source") or "manual")
    folder = _SOURCE_FOLDER.get(source_type, "manual")
    return _documents_root() / folder / f"{_slug(source_id)}.json"


def _materialize(row: dict[str, Any], *, actor: str) -> tuple[Path, bytes | None]:
    content = read_content(row)
    details = _document_details(row)
    path = _materialized_path(row)
    previous = path.read_bytes() if path.is_file() else None
    payload = {
        "source_id": str(details.get("source_id") or row.get("document_id") or ""),
        "source_type": str(details.get("source_type") or row.get("source") or "manual"),
        "title": str(details.get("title") or row.get("document_id") or ""),
        "content": content,
        "metadata": {
            **(details.get("metadata") if isinstance(details.get("metadata"), dict) else {}),
            "review_id": str(details.get("legacy_review_id") or row.get("document_id") or ""),
            "version": int(row.get("version") or 1),
            "status": "published",
            "published_at": _now(),
            "published_by": actor,
            "tenant_id": str(row.get("tenant_id") or ""),
            "store_id": str(row.get("store_id") or ""),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f".json.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return path, previous


def _restore_materialized(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    temp_path = path.with_suffix(f".restore.{os.getpid()}.tmp")
    try:
        temp_path.write_bytes(previous)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


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
    title: str = "",
    metadata: dict[str, Any] | None = None,
    legacy_review_id: str = "",
    legacy_version: int | None = None,
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
        history=[
            {
                "event": "created",
                "actor": actor,
                "at": _now(),
                "document": {
                    "source_id": doc_id,
                    "source_type": source,
                    "title": str(title or doc_id),
                    "metadata": dict(metadata or {}),
                    "legacy_review_id": str(legacy_review_id or ""),
                    "legacy_version": legacy_version,
                },
            }
        ],
    )
    row = _row(asset)
    row["size_bytes"] = len(content.encode("utf-8"))
    row["content_type"] = "text/plain"
    rows.append(row)
    _save_assets(rows)
    return asset


def submit_for_review(document_id: str, version: int, *, actor: str = "system") -> RagAssetVersion:
    return _transition(
        document_id,
        version,
        RagAssetStatus.REVIEW,
        allowed_from={RagAssetStatus.DRAFT},
        actor=actor,
        event="submitted",
    )


def approve(document_id: str, version: int, *, actor: str = "system") -> RagAssetVersion:
    return _transition(
        document_id,
        version,
        RagAssetStatus.APPROVED,
        allowed_from={RagAssetStatus.REVIEW},
        actor=actor,
        event="approved",
    )


def reject(document_id: str, version: int, *, reason: str = "", actor: str = "system") -> RagAssetVersion:
    return _transition(
        document_id,
        version,
        RagAssetStatus.REJECTED,
        allowed_from={RagAssetStatus.REVIEW},
        actor=actor,
        event="rejected",
        event_metadata={"reason": str(reason or "")[:500]},
    )


def retire(document_id: str, version: int, *, actor: str = "system") -> RagAssetVersion:
    current = next(
        (
            asset
            for asset in list_versions(document_id)
            if asset.version == int(version)
        ),
        None,
    )
    asset = _transition(
        document_id,
        version,
        RagAssetStatus.RETIRED,
        allowed_from={
            RagAssetStatus.DRAFT,
            RagAssetStatus.REVIEW,
            RagAssetStatus.APPROVED,
            RagAssetStatus.REJECTED,
            RagAssetStatus.PUBLISHED,
            RagAssetStatus.INDEXING,
            RagAssetStatus.INDEX_FAILED,
            RagAssetStatus.FAILED,
        },
        actor=actor,
        event="retired",
    )
    if current and current.status is RagAssetStatus.PUBLISHED:
        rag_governance_repository.clear_publication_pointer(
            document_id=document_id,
            version=int(version),
        )
    if any(
        item.document_id == document_id and item.status is RagAssetStatus.PUBLISHED
        for item in list_versions(document_id)
    ):
        return asset
    _materialized_path(_row(asset)).unlink(missing_ok=True)
    return asset


def start_indexing(document_id: str, version: int, *, actor: str = "system") -> RagAssetVersion:
    """Materialize a draft and mark it unavailable while its index is rebuilt."""

    rows = _load_assets()
    target = next(
        (
            row
            for row in rows
            if row.get("document_id") == document_id and int(row.get("version") or 0) == int(version)
        ),
        None,
    )
    if target is None:
        raise RagGovernanceError("asset_not_found")
    current = RagAssetStatus(str(target.get("status") or ""))
    if current not in {RagAssetStatus.DRAFT, RagAssetStatus.INDEX_FAILED}:
        raise RagGovernanceError("invalid_indexing_status")
    _materialize(target, actor=actor)
    return _transition(
        document_id,
        version,
        RagAssetStatus.INDEXING,
        allowed_from={RagAssetStatus.DRAFT, RagAssetStatus.INDEX_FAILED},
        actor=actor,
        event="indexing_started",
    )


def complete_indexing(document_id: str, version: int, *, actor: str = "system") -> RagAssetVersion:
    """Publish only after the background index build succeeds."""

    rows = _load_assets()
    target = None
    now = _now()
    for row in rows:
        if row.get("document_id") == document_id and int(row.get("version") or 0) == int(version):
            target = row
        elif row.get("document_id") == document_id and row.get("status") == RagAssetStatus.PUBLISHED.value:
            row["status"] = RagAssetStatus.RETIRED.value
            row["superseded_at"] = now
            row["history"] = [
                *(row.get("history") or []),
                {"event": "superseded", "actor": actor, "at": now},
            ]
    if target is None:
        raise RagGovernanceError("asset_not_found")
    if target.get("status") != RagAssetStatus.INDEXING.value:
        raise RagGovernanceError("invalid_index_complete_status")
    target["status"] = RagAssetStatus.PUBLISHED.value
    target["published_at"] = now
    target["published_by"] = actor
    target["history"] = [
        *(target.get("history") or []),
        {"event": "indexing_completed", "actor": actor, "at": now},
    ]
    _save_assets(rows)
    rag_governance_repository.set_publication_pointer(
        document_id=document_id,
        version=int(version),
        actor=actor,
        index_namespace=f"{document_id}@v{version}",
    )
    return _to_asset(target)


def fail_indexing(
    document_id: str,
    version: int,
    *,
    actor: str = "system",
    reason: str = "",
) -> RagAssetVersion:
    return _transition(
        document_id,
        version,
        RagAssetStatus.INDEX_FAILED,
        allowed_from={RagAssetStatus.INDEXING},
        actor=actor,
        event="indexing_failed",
        event_metadata={"reason": str(reason or "")[:500]},
    )


def publish(document_id: str, version: int, *, actor: str = "system") -> RagAssetVersion:
    rows = _load_assets()
    original_rows = copy.deepcopy(rows)
    target = None
    for row in rows:
        if row.get("document_id") == document_id and int(row.get("version") or 0) == int(version):
            target = row
            break
    if target is None:
        raise RagGovernanceError("asset_not_found")
    if target.get("status") != RagAssetStatus.APPROVED.value:
        raise RagGovernanceError("invalid_publish_status")
    materialized_path, previous_materialized = _materialize(target, actor=actor)
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
    try:
        _save_assets(rows)
        rag_governance_repository.set_publication_pointer(
            document_id=document_id,
            version=int(version),
            actor=actor,
            index_namespace=f"{document_id}@v{version}",
        )
    except Exception:
        _restore_materialized(materialized_path, previous_materialized)
        try:
            _save_assets(original_rows)
        except Exception:
            pass
        raise
    return _to_asset(target)


def rollback(document_id: str, to_version: int, *, actor: str = "system") -> RagAssetVersion:
    rows = _load_assets()
    original_rows = copy.deepcopy(rows)
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
    materialized_path, previous_materialized = _materialize(target, actor=actor)
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
    try:
        _save_assets(rows)
        rag_governance_repository.set_publication_pointer(
            document_id=document_id,
            version=int(to_version),
            actor=actor,
            index_namespace=f"{document_id}@v{to_version}",
        )
    except Exception:
        _restore_materialized(materialized_path, previous_materialized)
        try:
            _save_assets(original_rows)
        except Exception:
            pass
        raise
    return _to_asset(target)


def list_versions(document_id: str | None = None) -> list[RagAssetVersion]:
    assets = [_to_asset(row) for row in _load_assets()]
    if document_id:
        assets = [asset for asset in assets if asset.document_id == document_id]
    return sorted(assets, key=lambda asset: (asset.document_id, asset.version))


def list_published(document_id: str | None = None) -> list[RagAssetVersion]:
    return [asset for asset in list_versions(document_id) if asset.status is RagAssetStatus.PUBLISHED]


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


def _transition(
    document_id: str,
    version: int,
    status: RagAssetStatus,
    *,
    allowed_from: set[RagAssetStatus],
    actor: str,
    event: str,
    event_metadata: dict[str, Any] | None = None,
) -> RagAssetVersion:
    rows = _load_assets()
    for row in rows:
        if row.get("document_id") == document_id and int(row.get("version") or 0) == int(version):
            current = RagAssetStatus(str(row.get("status") or ""))
            if current not in allowed_from:
                raise RagGovernanceError(f"invalid_{event}_status")
            row["status"] = status.value
            if status in {RagAssetStatus.REVIEW, RagAssetStatus.APPROVED, RagAssetStatus.REJECTED}:
                row["reviewed_at"] = _now()
                row["reviewed_by"] = actor
            history = list(row.get("history") or [])
            history.append({"event": event, "actor": actor, "at": _now(), **(event_metadata or {})})
            row["history"] = history
            _save_assets(rows)
            return _to_asset(row)
    raise RagGovernanceError("asset_not_found")
