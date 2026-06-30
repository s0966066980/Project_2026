"""RAG source-document loading and rebuild helpers."""
import csv
import hashlib
import json
import os
import re
from pathlib import Path

import config
from services.rag_provider import get_rag

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".json", ".csv"}


def _documents_root() -> Path:
    configured = Path(config.RAG_DOCUMENTS_DIR)
    base = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return configured.resolve() if configured.is_absolute() else (base / configured).resolve()


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


def load_source_documents() -> list[dict]:
    root = _documents_root()
    if not root.exists():
        return []
    documents = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name.lower() == "readme.md":
            continue
        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            continue
        if extension in {".md", ".markdown", ".txt"}:
            documents.extend(_load_markdown_or_text(root, path))
        elif extension == ".json":
            documents.extend(_load_json(root, path))
        elif extension == ".csv":
            documents.extend(_load_csv(root, path))
    return documents


async def rebuild_from_source_documents() -> dict:
    documents = load_source_documents()
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
    return {
        "status": "ok" if not errors else "partial",
        "deleted": deleted,
        "imported": imported,
        "failed": len(errors),
        "errors": errors,
        "total": await rag.count(),
        "source_dir": str(_documents_root()),
    }
