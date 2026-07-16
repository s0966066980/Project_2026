"""RAG source-document loading and rebuild helpers."""
import csv
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

import config
from services import rag_alert_service
from services.rag_provider import get_rag

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".json", ".csv"}
ALLOWED_SOURCE_TYPES = {
    "manual",
    "policy",
    "faq",
    "menu_supplement",
    "promotion",
    "nutrition",
    "customer_service",
}


def _documents_root() -> Path:
    configured = Path(config.RAG_DOCUMENTS_DIR)
    base = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return configured.resolve() if configured.is_absolute() else (base / configured).resolve()


def _status_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "rag_rebuild_status.json"


def _selection_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "rag_index_selection.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_status(payload: dict) -> None:
    try:
        path = _status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        current = _read_status()
        current.update(payload)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    except Exception:
        pass


def _read_status() -> dict:
    try:
        data = json.loads(_status_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_source_ids(values) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    result = []
    seen = set()
    for value in values:
        source_id = str(value or "").strip()
        if source_id and source_id not in seen:
            seen.add(source_id)
            result.append(source_id)
    return result


def _read_selection() -> tuple[bool, list[str]]:
    path = _selection_path()
    if not path.exists():
        return False, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A damaged selection file must fail closed instead of restoring every source.
        return True, []
    if not isinstance(data, dict):
        return True, []
    return True, _normalize_source_ids(data.get("selected_source_ids"))


def _write_selection(source_ids: list[str]) -> list[str]:
    normalized = _normalize_source_ids(source_ids)
    path = _selection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(
            {"selected_source_ids": normalized, "updated_at": _now_iso()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
    return normalized


def _alert_payload(alert: dict | None, created: bool = False) -> dict:
    return {"created": created, "alert": alert or {}} if alert else {}


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return text[:96] or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _source_id(root: Path, path: Path, index: int | None = None) -> str:
    relative = path.relative_to(root)
    suffix = f"_{index}" if index is not None else ""
    return f"rag_{_slug(relative.as_posix())}{suffix}"


def _source_type(root: Path, path: Path, explicit: str | None = None) -> str:
    explicit = str(explicit or "").strip()
    if explicit:
        return explicit
    first = path.relative_to(root).parts[0]
    mapping = {
        "faq": "faq",
        "menu": "menu_supplement",
        "promotions": "promotion",
        "nutrition": "nutrition",
        "store_policy": "policy",
        "customer_service": "customer_service",
    }
    return mapping.get(first, "manual")


def _markdown_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def _format_dict(row: dict) -> str:
    lines = []
    for key, value in row.items():
        if value is None or value == "":
            continue
        if isinstance(value, str):
            value = value.strip()
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}：{value}")
    return "\n".join(lines)


def _load_markdown_or_text(root: Path, path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return [{
        "content": content,
        "source_id": _source_id(root, path),
        "source_type": _source_type(root, path),
        "metadata": {
            "path": path.relative_to(root).as_posix(),
            "title": _markdown_title(content, path.stem),
            "format": path.suffix.lstrip("."),
        },
    }]


def _load_json(root: Path, path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else [data]
    docs = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            content = str(row).strip()
            metadata = {}
            explicit_type = None
            explicit_id = None
        else:
            content = str(row.get("content") or "").strip() or _format_dict(row)
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            explicit_type = row.get("source_type")
            explicit_id = row.get("source_id")
        if not content:
            continue
        docs.append({
            "content": content,
            "source_id": str(explicit_id).strip() if explicit_id else _source_id(root, path, index),
            "source_type": _source_type(root, path, str(explicit_type) if explicit_type else None),
            "metadata": {
                "path": path.relative_to(root).as_posix(),
                "format": "json",
                "row_index": index,
                **metadata,
            },
        })
    return docs


def _load_csv(root: Path, path: Path) -> list[dict]:
    docs = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            content = str(row.get("content") or "").strip() or _format_dict(row)
            if not content:
                continue
            docs.append({
                "content": content,
                "source_id": str(row.get("source_id") or _source_id(root, path, index)).strip(),
                "source_type": _source_type(root, path, row.get("source_type") or None),
                "metadata": {
                    "path": path.relative_to(root).as_posix(),
                    "format": "csv",
                    "row_index": index,
                    "title": row.get("title") or row.get("name") or "",
                },
            })
    return docs


def _iter_source_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.startswith(".") and path.name.lower() != "readme.md"
    ]


def _load_documents_from_path(root: Path, path: Path) -> list[dict]:
    extension = path.suffix.lower()
    if extension in {".md", ".markdown", ".txt"}:
        return _load_markdown_or_text(root, path)
    if extension == ".json":
        return _load_json(root, path)
    if extension == ".csv":
        return _load_csv(root, path)
    return []


def _issue(level: str, path: Path | None, message: str, source_id: str = "") -> dict:
    root = _documents_root()
    try:
        relative_path = path.relative_to(root).as_posix() if path else ""
    except Exception:
        relative_path = path.as_posix() if path else ""
    return {
        "level": level,
        "path": relative_path,
        "source_id": source_id,
        "message": message,
    }


def _validate_promotion_document(document: dict, path: Path, errors: list[dict], warnings: list[dict]) -> None:
    try:
        from services import promotion_service
    except Exception as exc:
        warnings.append(_issue("warning", path, f"無法載入 promotion validator：{exc}", document.get("source_id", "")))
        return

    raw_metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    if path.parent.name != "promotions":
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(_issue("error", path, f"promotion JSON 無法解析：{exc}", document.get("source_id", "")))
        return
    rows = data if isinstance(data, list) else [data]
    row_index = int(raw_metadata.get("row_index", 0) or 0)
    if row_index >= len(rows) or not isinstance(rows[row_index], dict):
        errors.append(_issue("error", path, "promotion row 必須是 object", document.get("source_id", "")))
        return
    row = rows[row_index]
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    status = str(row.get("status") or metadata.get("status") or "").strip().lower()
    if status in {"example", "draft", "inactive", "disabled", "archived"}:
        warnings.append(_issue("warning", path, f"promotion 狀態為 {status or 'draft'}，會進入 Chroma 但不會影響推薦", document.get("source_id", "")))
        return
    _, validation_errors = promotion_service.validate_promotion_payload(row)
    for message in validation_errors:
        errors.append(_issue("error", path, f"promotion 驗證失敗：{message}", document.get("source_id", "")))


def validate_source_documents(include_documents: bool = False) -> dict:
    root = _documents_root()
    errors: list[dict] = []
    warnings: list[dict] = []
    documents: list[dict] = []
    file_count = 0

    if not root.exists():
        errors.append(_issue("error", root, "RAG source directory 不存在"))
        result = {
            "status": "error",
            "ok": False,
            "source_dir": str(root),
            "total_files": 0,
            "total_documents": 0,
            "valid_documents": 0,
            "errors": errors,
            "warnings": warnings,
            "documents": [],
            "checked_at": _now_iso(),
        }
        _write_status({"last_validation": result})
        return result

    source_ids: dict[str, str] = {}
    for path in _iter_source_files(root):
        file_count += 1
        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            warnings.append(_issue("warning", path, f"不支援的副檔名 {extension or '(none)'}，已略過"))
            continue
        try:
            loaded = _load_documents_from_path(root, path)
        except Exception as exc:
            errors.append(_issue("error", path, f"文件解析失敗：{exc}"))
            continue
        if not loaded:
            warnings.append(_issue("warning", path, "文件內容為空或沒有可匯入資料"))
            continue
        for document in loaded:
            source_id = str(document.get("source_id") or "").strip()
            source_type = str(document.get("source_type") or "").strip()
            content = str(document.get("content") or "").strip()
            if not source_id:
                errors.append(_issue("error", path, "source_id 不可為空"))
                continue
            if source_id in source_ids:
                errors.append(_issue("error", path, f"source_id 重複，已存在於 {source_ids[source_id]}", source_id))
                continue
            if not content:
                errors.append(_issue("error", path, "content 不可為空", source_id))
                continue
            if source_type not in ALLOWED_SOURCE_TYPES:
                warnings.append(_issue("warning", path, f"未知 source_type `{source_type}`，會以 manual 類型處理", source_id))
                document["source_type"] = "manual"
            _validate_promotion_document(document, path, errors, warnings)
            source_ids[source_id] = path.relative_to(root).as_posix()
            documents.append(document)

    ok = not errors
    preview_documents = []
    if include_documents:
        for document in documents:
            metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
            preview_documents.append({
                "source_id": document.get("source_id", ""),
                "source_type": document.get("source_type", ""),
                "path": metadata.get("path", ""),
                "title": metadata.get("title", ""),
                "format": metadata.get("format", ""),
                "content_preview": str(document.get("content") or "")[:160],
            })
    selection_configured, selected_source_ids = _read_selection()
    result = {
        "status": "ok" if ok else "error",
        "ok": ok,
        "source_dir": str(root),
        "total_files": file_count,
        "total_documents": len(documents),
        "valid_documents": len(documents) if ok else 0,
        "errors": errors,
        "warnings": warnings,
        "documents": preview_documents,
        "selection_configured": selection_configured,
        "selected_source_ids": selected_source_ids,
        "checked_at": _now_iso(),
    }
    _write_status({"last_validation": result})
    return result


def load_source_documents() -> list[dict]:
    root = _documents_root()
    if not root.exists():
        return []
    documents = []
    for path in _iter_source_files(root):
        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            continue
        documents.extend(_load_documents_from_path(root, path))
    return documents


async def rebuild_from_source_documents(selected_source_ids: list[str] | None = None) -> dict:
    validation = validate_source_documents(include_documents=False)
    if not validation.get("ok"):
        alert, created = rag_alert_service.create_alert(
            "rag_rebuild_validation_failed",
            severity="error",
            message="RAG rebuild validation failed; Chroma was not cleared.",
            errors=validation.get("errors", []),
            source_dir=validation.get("source_dir", str(_documents_root())),
            metadata={
                "total_files": validation.get("total_files", 0),
                "total_documents": validation.get("total_documents", 0),
            },
        )
        result = {
            "status": "error",
            "deleted": 0,
            "imported": 0,
            "failed": len(validation.get("errors", [])),
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "total": None,
            "source_dir": validation.get("source_dir", str(_documents_root())),
            "validated": validation,
            "rebuild_at": _now_iso(),
            "alert": _alert_payload(alert, created),
        }
        _write_status({"last_validation": validation, "last_rebuild": result})
        return result

    documents = load_source_documents()
    available_ids = {str(document.get("source_id") or "") for document in documents}
    selection_configured, saved_source_ids = _read_selection()
    if selected_source_ids is not None:
        resolved_source_ids = _normalize_source_ids(selected_source_ids)
        selection_source = "request"
    elif selection_configured:
        resolved_source_ids = saved_source_ids
        selection_source = "saved"
    else:
        resolved_source_ids = [str(document.get("source_id") or "") for document in documents]
        selection_source = "all_sources"

    missing_source_ids = [source_id for source_id in resolved_source_ids if source_id not in available_ids]
    if missing_source_ids and selected_source_ids is not None:
        errors = [
            _issue("error", None, "選取的來源文件已不存在，請重新檢查並選取", source_id)
            for source_id in missing_source_ids
        ]
        result = {
            "status": "error",
            "deleted": 0,
            "imported": 0,
            "failed": len(errors),
            "errors": errors,
            "warnings": validation.get("warnings", []),
            "total": None,
            "source_dir": str(_documents_root()),
            "selected_source_ids": resolved_source_ids,
            "selection_source": selection_source,
            "validated": validation,
            "rebuild_at": _now_iso(),
        }
        _write_status({"last_validation": validation, "last_rebuild": result})
        return result

    selection_warnings = []
    if missing_source_ids:
        selection_warnings = [
            _issue("warning", None, "已從正式選取移除不存在的來源文件", source_id)
            for source_id in missing_source_ids
        ]
        resolved_source_ids = _write_selection(
            [source_id for source_id in resolved_source_ids if source_id in available_ids]
        )

    selected_set = set(resolved_source_ids)
    documents = [document for document in documents if document.get("source_id") in selected_set]
    if selected_source_ids is not None:
        resolved_source_ids = _write_selection(resolved_source_ids)
    rag = get_rag()
    deleted = await rag.clear_all()
    imported = 0
    errors = []
    for document in documents:
        try:
            await rag.add_document(
                content=document["content"],
                source_id=document["source_id"],
                source_type=document["source_type"],
                metadata=document["metadata"],
            )
            imported += 1
        except Exception as exc:
            errors.append({
                "source_id": document.get("source_id", ""),
                "message": str(exc),
            })
    result = {
        "status": "ok" if not errors else "partial",
        "deleted": deleted,
        "imported": imported,
        "failed": len(errors),
        "errors": errors,
        "warnings": [*validation.get("warnings", []), *selection_warnings],
        "total": await rag.count(),
        "source_dir": str(_documents_root()),
        "selected_source_ids": resolved_source_ids,
        "selection_source": selection_source,
        "validated": validation,
        "rebuild_at": _now_iso(),
    }
    if errors:
        alert, created = rag_alert_service.create_alert(
            "rag_rebuild_partial_failed",
            severity="warning",
            message="RAG rebuild completed with failed document imports.",
            errors=errors,
            source_dir=str(_documents_root()),
            metadata={"imported": imported, "failed": len(errors), "deleted": deleted},
        )
        result["alert"] = _alert_payload(alert, created)
    else:
        rag_alert_service.resolve_alerts_by_type("rag_rebuild_validation_failed")
        rag_alert_service.resolve_alerts_by_type("rag_rebuild_partial_failed")
    _write_status({"last_validation": validation, "last_rebuild": result})
    return result


async def clear_index() -> dict:
    """Clear Chroma and persist an explicit empty selection to prevent old sources returning."""
    selected_source_ids = _write_selection([])
    deleted = await get_rag().clear_all()
    return {
        "status": "ok",
        "deleted": deleted,
        "selected_source_ids": selected_source_ids,
        "selection_source": "saved",
    }


def exclude_source_from_index(source_id: str) -> list[str]:
    """Remove one source from the durable selection without deleting its source file."""
    normalized_id = str(source_id or "").strip()
    selection_configured, selected_source_ids = _read_selection()
    if not selection_configured:
        selected_source_ids = [
            str(document.get("source_id") or "")
            for document in load_source_documents()
        ]
    return _write_selection([row for row in selected_source_ids if row != normalized_id])


async def health_status() -> dict:
    root = _documents_root()
    chroma_path = Path(config.RAG_CHROMA_DIR)
    collection_ok = True
    collection_error = ""
    doc_count = 0
    try:
        doc_count = await get_rag().count()
    except Exception as exc:
        collection_ok = False
        collection_error = str(exc)
    source_readable = root.exists() and os.access(root, os.R_OK)
    chroma_parent = chroma_path if chroma_path.exists() else chroma_path.parent
    chroma_writable = chroma_parent.exists() and os.access(chroma_parent, os.W_OK)
    status = _read_status()
    selection_configured, selected_source_ids = _read_selection()
    status_value = "ok" if collection_ok and source_readable and chroma_writable else "degraded"
    alert_info = {}
    if status_value == "degraded":
        alert, created = rag_alert_service.create_alert(
            "rag_health_degraded",
            severity="warning",
            message="RAG health check is degraded.",
            errors=[{"message": collection_error}] if collection_error else [],
            source_dir=str(root),
            metadata={
                "collection_ok": collection_ok,
                "source_dir_exists": root.exists(),
                "source_dir_readable": source_readable,
                "chroma_writable": chroma_writable,
            },
        )
        alert_info = _alert_payload(alert, created)
    else:
        rag_alert_service.resolve_alerts_by_type("rag_health_degraded")
    return {
        "status": status_value,
        "enabled": bool(config.get("RAG_ENABLED", False)),
        "doc_count": doc_count,
        "collection_ok": collection_ok,
        "collection_error": collection_error,
        "source_dir_exists": root.exists(),
        "source_dir_readable": source_readable,
        "chroma_writable": chroma_writable,
        "chroma_path": str(chroma_path.resolve()),
        "collection_name": str(config.RAG_COLLECTION),
        "source_dir": str(root),
        "selection_configured": selection_configured,
        "selected_source_ids": selected_source_ids,
        "selected_source_count": len(selected_source_ids),
        "last_validation": status.get("last_validation", {}),
        "last_rebuild": status.get("last_rebuild", {}),
        "alert": alert_info,
    }
