"""Thirty-day, media-free emotion analysis record store."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone

import config

_RECORD_PATH = os.path.join(config.LEARNING_DATA_DIR, "emotion_analysis_records.json")
_lock = threading.Lock()


def _timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _load_unlocked() -> list[dict]:
    try:
        with open(_RECORD_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _pruned(rows: list[dict]) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    return [row for row in rows if (parsed := _timestamp(row.get("timestamp"))) and parsed >= cutoff]


def _write_unlocked(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(_RECORD_PATH), exist_ok=True)
    temp_path = f"{_RECORD_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, _RECORD_PATH)


def append_record(entry: dict) -> dict:
    with _lock:
        rows = _pruned(_load_unlocked())
        rows.append(dict(entry))
        _write_unlocked(rows)
    return entry


def get_records(limit: int = 200) -> list[dict]:
    with _lock:
        rows = _pruned(_load_unlocked())
        _write_unlocked(rows)
    return list(reversed(rows[-max(1, min(int(limit), 1000)):]))


def clear_records() -> int:
    with _lock:
        count = len(_load_unlocked())
        _write_unlocked([])
    return count
