"""JSON-backed structured promotion repository."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import config


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
    return save_promotion_at_path(promotion_path(promotion_id), data)


def delete_promotion(promotion_id: str, *, is_valid_id) -> bool:
    path = find_promotion_path(promotion_id, is_valid_id=is_valid_id)
    if not path:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
