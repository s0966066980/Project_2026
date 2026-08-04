"""Legacy RAG review contract backed by the canonical governed-document lifecycle."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from models.rag_governance import RagAssetStatus, RagAssetVersion
from services import rag_governance_service

ALLOWED_REVIEW_SOURCE_TYPES = {
    "manual",
    "policy",
    "faq",
    "menu_supplement",
    "promotion",
    "nutrition",
    "customer_service",
}
REVIEW_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,120}$")
SOURCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,120}$")


def _documents_root() -> Path:
    configured = Path(config.RAG_DOCUMENTS_DIR)
    base = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return configured.resolve() if configured.is_absolute() else (base / configured).resolve()


def _queue_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "rag_review_queue.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slug(value: str, limit: int = 96) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "")).strip("_").lower()
    return text[:limit] or hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:12]


def _safe_text(value: Any, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def _load_queue() -> list[dict]:
    try:
        data = json.loads(_queue_path().read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data if isinstance(data, list) else data.get("reviews", []) if isinstance(data, dict) else []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _folder_for_source_type(source_type: str) -> str:
    return {
        "faq": "faq",
        "policy": "store_policy",
        "menu_supplement": "menu",
        "nutrition": "nutrition",
        "customer_service": "customer_service",
        "promotion": "promotion_notes",
        "manual": "manual",
    }.get(source_type, "manual")


def _published_path(source_type: str, source_id: str) -> Path:
    folder = _folder_for_source_type(source_type)
    return _documents_root() / folder / f"{_slug(source_id, 120)}.json"


def _validate_payload(payload: dict, *, existing: dict | None = None) -> tuple[dict | None, list[str]]:
    raw = payload if isinstance(payload, dict) else {}
    errors: list[str] = []
    source_id = _safe_text(raw.get("source_id") or (existing or {}).get("source_id"), 140)
    if not SOURCE_ID_PATTERN.match(source_id):
        errors.append("source_id 必須為 3-121 字元，只能使用英數、底線或連字號，且需以英數開頭")

    source_type = _safe_text(raw.get("source_type") or (existing or {}).get("source_type") or "manual", 40)
    if source_type not in ALLOWED_REVIEW_SOURCE_TYPES:
        errors.append("source_type 不支援")

    content = _safe_text(raw.get("content") if "content" in raw else (existing or {}).get("content"), 12000)
    if not content:
        errors.append("content 不可為空")

    title = _safe_text(raw.get("title") or (existing or {}).get("title") or source_id, 160)
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else (existing or {}).get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    if errors:
        return None, errors

    return {
        "source_id": source_id,
        "source_type": source_type,
        "title": title,
        "content": content,
        "metadata": {
            **metadata,
            "title": title,
            "category": metadata.get("category") or source_type,
        },
    }, []


def _validate_review_for_publish(record: dict) -> list[str]:
    _, errors = _validate_payload(record, existing=record)
    if errors:
        return errors
    try:
        from services import rag_document_service
        temp_path = _published_path(record["source_type"], record["source_id"])
        document = {
            "content": record["content"],
            "source_id": record["source_id"],
            "source_type": record["source_type"],
            "metadata": {
                "path": temp_path.relative_to(_documents_root()).as_posix(),
                "format": "json",
                "title": record["title"],
                **(record.get("metadata") if isinstance(record.get("metadata"), dict) else {}),
            },
        }
        if document["source_type"] not in rag_document_service.ALLOWED_SOURCE_TYPES:
            return ["source_type 不支援"]
    except Exception as exc:
        return [f"發布前驗證失敗：{exc}"]
    return []


def _details(asset: RagAssetVersion) -> dict[str, Any]:
    for event in asset.history:
        if event.get("event") == "created" and isinstance(event.get("document"), dict):
            return dict(event["document"])
    return {}


def _review_id(asset: RagAssetVersion) -> str:
    return str(_details(asset).get("legacy_review_id") or asset.document_id)


def _event(asset: RagAssetVersion, event_name: str) -> dict[str, Any]:
    return next((dict(event) for event in reversed(asset.history) if event.get("event") == event_name), {})


def _legacy_status(status: RagAssetStatus) -> str:
    return {
        RagAssetStatus.REVIEW: "draft",
        RagAssetStatus.RETIRED: "archived",
    }.get(status, status.value)


def _record(asset: RagAssetVersion) -> dict[str, Any]:
    details = _details(asset)
    approved = _event(asset, "approved")
    rejected = _event(asset, "rejected")
    published = _event(asset, "published") or _event(asset, "rollback_publish")
    updated = asset.history[-1] if asset.history else {}
    source_type = str(details.get("source_type") or asset.source or "manual")
    source_id = str(details.get("source_id") or asset.document_id)
    published_path = _published_path(source_type, source_id)
    return {
        "review_id": _review_id(asset),
        "source_id": source_id,
        "source_type": source_type,
        "title": str(details.get("title") or source_id),
        "content": rag_governance_service.read_content(asset),
        "metadata": dict(details.get("metadata") or {}),
        "status": _legacy_status(asset.status),
        "version": asset.version,
        "created_at": asset.created_at,
        "updated_at": str(updated.get("at") or asset.created_at),
        "created_by": str((asset.history[0] if asset.history else {}).get("actor") or asset.owner),
        "updated_by": str(updated.get("actor") or asset.owner),
        "approved_at": str(approved.get("at") or ""),
        "approved_by": str(approved.get("actor") or ""),
        "published_at": asset.published_at or str(published.get("at") or ""),
        "published_by": str(published.get("actor") or ""),
        "published_path": (
            published_path.relative_to(_documents_root()).as_posix()
            if published_path.is_file()
            else ""
        ),
        "rejection_reason": str(rejected.get("reason") or ""),
        "history": list(asset.history)[-8:],
    }


def _latest_assets() -> dict[str, RagAssetVersion]:
    latest: dict[str, RagAssetVersion] = {}
    for asset in rag_governance_service.list_versions():
        review_id = _review_id(asset)
        if review_id not in latest or asset.version > latest[review_id].version:
            latest[review_id] = asset
    return latest


def _apply_imported_status(asset: RagAssetVersion, status: str, *, actor: str, reason: str = "") -> None:
    normalized = str(status or "draft")
    if normalized == "draft":
        return
    if normalized == "archived":
        rag_governance_service.retire(asset.document_id, asset.version, actor=actor)
        return
    reviewed = rag_governance_service.submit_for_review(asset.document_id, asset.version, actor=actor)
    if normalized == "review":
        return
    if normalized == "rejected":
        rag_governance_service.reject(
            reviewed.document_id,
            reviewed.version,
            reason=reason,
            actor=actor,
        )
        return
    approved = rag_governance_service.approve(reviewed.document_id, reviewed.version, actor=actor)
    if normalized == "published":
        rag_governance_service.publish(approved.document_id, approved.version, actor=actor)


def _ensure_legacy_imported() -> None:
    legacy_rows = _load_queue()
    if not legacy_rows:
        return
    imported = {
        (_review_id(asset), int(_details(asset).get("legacy_version") or asset.version))
        for asset in rag_governance_service.list_versions()
        if _details(asset).get("legacy_review_id")
    }
    for row in legacy_rows:
        review_id = str(row.get("review_id") or row.get("source_id") or "")
        snapshots = [
            {**row, **history_row, "history": []}
            for history_row in (row.get("history") or [])
            if isinstance(history_row, dict) and history_row.get("content")
        ]
        snapshots.append(dict(row))
        snapshots.sort(key=lambda item: int(item.get("version") or 1))
        for snapshot in snapshots:
            legacy_version = int(snapshot.get("version") or 1)
            if (review_id, legacy_version) in imported:
                continue
            normalized, errors = _validate_payload(snapshot, existing=row)
            if errors or not normalized:
                raise rag_governance_service.RagGovernanceError(
                    f"legacy_review_import_invalid:{review_id}:{';'.join(errors)}"
                )
            actor = str(snapshot.get("updated_by") or snapshot.get("created_by") or "legacy-import")
            asset = rag_governance_service.create_draft(
                document_id=normalized["source_id"],
                content=normalized["content"],
                source=normalized["source_type"],
                owner=actor,
                tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
                store_id=LEGACY_DEFAULT_SCOPE.store_id,
                actor=actor,
                title=normalized["title"],
                metadata=normalized["metadata"],
                legacy_review_id=review_id,
                legacy_version=legacy_version,
            )
            _apply_imported_status(
                asset,
                str(snapshot.get("status") or "draft"),
                actor=actor,
                reason=str(snapshot.get("rejection_reason") or ""),
            )
            imported.add((review_id, legacy_version))


def list_reviews(status: str = "") -> list[dict]:
    _ensure_legacy_imported()
    rows = [_record(asset) for asset in _latest_assets().values()]
    status_filter = _safe_text(status, 40)
    if status_filter:
        rows = [row for row in rows if row.get("status") == status_filter]
    rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    return rows


def create_review(payload: dict, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    _ensure_legacy_imported()
    normalized, errors = _validate_payload(payload)
    if errors or not normalized:
        return None, errors
    review_id = _safe_text(payload.get("review_id"), 140) if isinstance(payload, dict) else ""
    if review_id and not REVIEW_ID_PATTERN.match(review_id):
        return None, ["review_id 必須為 3-121 字元，只能使用英數、底線或連字號，且需以英數開頭"]
    review_id = review_id or f"rag_review_{_now_iso().replace(':', '').replace('-', '').replace('T', '_')}_{_slug(normalized['source_id'], 24)}"
    latest = _latest_assets()
    if review_id in latest:
        return None, ["review_id 已存在"]
    if any(
        asset.document_id == normalized["source_id"]
        and asset.status in {RagAssetStatus.DRAFT, RagAssetStatus.REVIEW, RagAssetStatus.APPROVED}
        for asset in latest.values()
    ):
        return None, ["已有同 source_id 的待審核或已核准草稿"]
    try:
        asset = rag_governance_service.create_draft(
            document_id=normalized["source_id"],
            content=normalized["content"],
            source=normalized["source_type"],
            owner=actor,
            tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
            store_id=LEGACY_DEFAULT_SCOPE.store_id,
            actor=actor,
            title=normalized["title"],
            metadata=normalized["metadata"],
            legacy_review_id=review_id,
        )
        return _record(asset), []
    except rag_governance_service.RagGovernanceError as exc:
        return None, [str(exc)]


def update_review(review_id: str, payload: dict, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    _ensure_legacy_imported()
    existing_asset = _latest_assets().get(review_id)
    if not existing_asset:
        return None, ["review_id 不存在"]
    if existing_asset.status is RagAssetStatus.RETIRED:
        return None, ["已封存文件不可編輯"]
    existing = _record(existing_asset)
    normalized, errors = _validate_payload(payload, existing=existing)
    if errors or not normalized:
        return None, errors
    if all(
        normalized[key] == existing.get(key)
        for key in ("source_id", "source_type", "title", "content", "metadata")
    ):
        return existing, []
    try:
        asset = rag_governance_service.create_draft(
            document_id=existing_asset.document_id,
            content=normalized["content"],
            source=normalized["source_type"],
            owner=actor,
            tenant_id=existing_asset.tenant_id,
            store_id=existing_asset.store_id,
            actor=actor,
            title=normalized["title"],
            metadata=normalized["metadata"],
            legacy_review_id=review_id,
        )
        return _record(asset), []
    except rag_governance_service.RagGovernanceError as exc:
        return None, [str(exc)]


def approve_review(review_id: str, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    _ensure_legacy_imported()
    asset = _latest_assets().get(review_id)
    if not asset:
        return None, ["review_id 不存在"]
    if asset.status is RagAssetStatus.APPROVED:
        return _record(asset), []
    if asset.status is not RagAssetStatus.DRAFT:
        return None, ["只有 draft 文件可核准；rejected 文件需建立新版本"]
    record = _record(asset)
    errors = _validate_review_for_publish(record)
    if errors:
        return None, errors
    try:
        reviewed = rag_governance_service.submit_for_review(asset.document_id, asset.version, actor=actor)
        approved = rag_governance_service.approve(reviewed.document_id, reviewed.version, actor=actor)
        return _record(approved), []
    except rag_governance_service.RagGovernanceError as exc:
        return None, [str(exc)]


def publish_review(review_id: str, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    _ensure_legacy_imported()
    asset = _latest_assets().get(review_id)
    if not asset:
        return None, ["review_id 不存在"]
    if asset.status is RagAssetStatus.PUBLISHED:
        return _record(asset), []
    if asset.status is not RagAssetStatus.APPROVED:
        return None, ["文件需先核准才可發布"]
    try:
        return _record(rag_governance_service.publish(asset.document_id, asset.version, actor=actor)), []
    except rag_governance_service.RagGovernanceError as exc:
        return None, [str(exc)]


def reject_review(review_id: str, reason: str = "", *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    _ensure_legacy_imported()
    asset = _latest_assets().get(review_id)
    if not asset:
        return None, ["review_id 不存在"]
    if asset.status is RagAssetStatus.DRAFT:
        asset = rag_governance_service.submit_for_review(asset.document_id, asset.version, actor=actor)
    if asset.status is not RagAssetStatus.REVIEW:
        return None, ["只有待審核文件可拒絕"]
    try:
        rejected = rag_governance_service.reject(
            asset.document_id,
            asset.version,
            reason=_safe_text(reason, 500),
            actor=actor,
        )
        return _record(rejected), []
    except rag_governance_service.RagGovernanceError as exc:
        return None, [str(exc)]


def archive_review(review_id: str, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    _ensure_legacy_imported()
    asset = _latest_assets().get(review_id)
    if not asset:
        return None, ["review_id 不存在"]
    if asset.status is RagAssetStatus.RETIRED:
        return _record(asset), []
    try:
        return _record(rag_governance_service.retire(asset.document_id, asset.version, actor=actor)), []
    except rag_governance_service.RagGovernanceError as exc:
        return None, [str(exc)]
