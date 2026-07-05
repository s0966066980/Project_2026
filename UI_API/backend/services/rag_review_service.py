"""RAG document review and publishing workflow.

Draft records are stored in runtime JSON. Published records are written back to
rag_documents so Chroma can always be rebuilt from source files.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import config

ALLOWED_REVIEW_SOURCE_TYPES = {
    "manual",
    "policy",
    "faq",
    "menu_supplement",
    "promotion",
    "nutrition",
    "customer_service",
}
EDITABLE_STATUSES = {"draft", "rejected", "approved", "published"}
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


def _write_queue(rows: list[dict]) -> None:
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".json.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


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


def _public_record(record: dict) -> dict:
    public = dict(record)
    public["history"] = list(public.get("history") or [])[-8:]
    return public


def _find_review(rows: list[dict], review_id: str) -> tuple[int, dict | None]:
    for index, row in enumerate(rows):
        if row.get("review_id") == review_id:
            return index, row
    return -1, None


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


def list_reviews(status: str = "") -> list[dict]:
    rows = _load_queue()
    status_filter = _safe_text(status, 40)
    if status_filter:
        rows = [row for row in rows if row.get("status") == status_filter]
    rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    return [_public_record(row) for row in rows]


def create_review(payload: dict, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    normalized, errors = _validate_payload(payload)
    if errors or not normalized:
        return None, errors
    rows = _load_queue()
    review_id = _safe_text(payload.get("review_id"), 140) if isinstance(payload, dict) else ""
    if review_id and not REVIEW_ID_PATTERN.match(review_id):
        return None, ["review_id 必須為 3-121 字元，只能使用英數、底線或連字號，且需以英數開頭"]
    review_id = review_id or f"rag_review_{_now_iso().replace(':', '').replace('-', '').replace('T', '_')}_{_slug(normalized['source_id'], 24)}"
    if any(row.get("review_id") == review_id for row in rows):
        return None, ["review_id 已存在"]
    if any(row.get("source_id") == normalized["source_id"] and row.get("status") in {"draft", "approved"} for row in rows):
        return None, ["已有同 source_id 的待審核或已核准草稿"]
    now = _now_iso()
    record = {
        "review_id": review_id,
        **normalized,
        "status": "draft",
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "created_by": actor,
        "updated_by": actor,
        "approved_at": "",
        "approved_by": "",
        "published_at": "",
        "published_by": "",
        "published_path": "",
        "rejection_reason": "",
        "history": [],
    }
    rows.append(record)
    _write_queue(rows)
    return _public_record(record), []


def update_review(review_id: str, payload: dict, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    rows = _load_queue()
    index, existing = _find_review(rows, review_id)
    if not existing:
        return None, ["review_id 不存在"]
    if existing.get("status") == "archived":
        return None, ["已封存文件不可編輯"]
    normalized, errors = _validate_payload(payload, existing=existing)
    if errors or not normalized:
        return None, errors
    now = _now_iso()
    history = list(existing.get("history") or [])
    history.append({
        "version": existing.get("version", 1),
        "status": existing.get("status", ""),
        "title": existing.get("title", ""),
        "content": existing.get("content", ""),
        "updated_at": existing.get("updated_at", ""),
        "updated_by": existing.get("updated_by", ""),
    })
    version = int(existing.get("version") or 1)
    if (
        normalized["content"] != existing.get("content")
        or normalized["title"] != existing.get("title")
        or normalized["source_type"] != existing.get("source_type")
    ):
        version += 1
    updated = {
        **existing,
        **normalized,
        "status": "draft",
        "version": version,
        "updated_at": now,
        "updated_by": actor,
        "approved_at": "",
        "approved_by": "",
        "rejection_reason": "",
        "history": history[-20:],
    }
    rows[index] = updated
    _write_queue(rows)
    return _public_record(updated), []


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


def approve_review(review_id: str, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    rows = _load_queue()
    index, record = _find_review(rows, review_id)
    if not record:
        return None, ["review_id 不存在"]
    if record.get("status") not in {"draft", "rejected"}:
        return None, ["只有 draft 或 rejected 文件可核准"]
    errors = _validate_review_for_publish(record)
    if errors:
        return None, errors
    now = _now_iso()
    updated = {
        **record,
        "status": "approved",
        "approved_at": now,
        "approved_by": actor,
        "updated_at": now,
        "updated_by": actor,
        "rejection_reason": "",
    }
    rows[index] = updated
    _write_queue(rows)
    return _public_record(updated), []


def _write_published_file(record: dict) -> str:
    path = _published_path(record["source_type"], record["source_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_id": record["source_id"],
        "source_type": record["source_type"],
        "title": record["title"],
        "content": record["content"],
        "metadata": {
            **(record.get("metadata") if isinstance(record.get("metadata"), dict) else {}),
            "review_id": record["review_id"],
            "version": record.get("version", 1),
            "status": "published",
            "published_at": _now_iso(),
        },
    }
    tmp_path = path.with_suffix(f".json.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)
    return path.relative_to(_documents_root()).as_posix()


def publish_review(review_id: str, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    rows = _load_queue()
    index, record = _find_review(rows, review_id)
    if not record:
        return None, ["review_id 不存在"]
    if record.get("status") not in {"approved", "published"}:
        return None, ["文件需先核准才可發布"]
    errors = _validate_review_for_publish(record)
    if errors:
        return None, errors
    now = _now_iso()
    published_path = _write_published_file(record)
    updated = {
        **record,
        "status": "published",
        "published_at": now,
        "published_by": actor,
        "published_path": published_path,
        "updated_at": now,
        "updated_by": actor,
    }
    rows[index] = updated
    _write_queue(rows)
    return _public_record(updated), []


def reject_review(review_id: str, reason: str = "", *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    rows = _load_queue()
    index, record = _find_review(rows, review_id)
    if not record:
        return None, ["review_id 不存在"]
    if record.get("status") in {"published", "archived"}:
        return None, ["已發布或封存文件不可拒絕"]
    now = _now_iso()
    updated = {
        **record,
        "status": "rejected",
        "rejection_reason": _safe_text(reason, 500),
        "updated_at": now,
        "updated_by": actor,
    }
    rows[index] = updated
    _write_queue(rows)
    return _public_record(updated), []


def archive_review(review_id: str, *, actor: str = "admin") -> tuple[dict | None, list[str]]:
    rows = _load_queue()
    index, record = _find_review(rows, review_id)
    if not record:
        return None, ["review_id 不存在"]
    now = _now_iso()
    updated = {
        **record,
        "status": "archived",
        "updated_at": now,
        "updated_by": actor,
    }
    rows[index] = updated
    _write_queue(rows)
    return _public_record(updated), []
