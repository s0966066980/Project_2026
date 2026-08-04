"""Authoritative source selection shared by RAG rebuild and query paths."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import config


def _path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "rag_index_selection.json"


def normalize(values) -> list[str]:
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


def read() -> tuple[bool, list[str]]:
    """Return (configured, ids); corrupt state is configured-empty and therefore fail-closed."""
    path = _path()
    if not path.exists():
        return False, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, []
    if not isinstance(data, dict):
        return True, []
    return True, normalize(data.get("selected_source_ids"))


def write(source_ids: list[str]) -> list[str]:
    normalized = normalize(source_ids)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {
                "selected_source_ids": normalized,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return normalized
