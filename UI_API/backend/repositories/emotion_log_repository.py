"""emotion_intervention_logs.json 讀寫。"""
import json
import os
import threading

import config

_LOG_PATH = os.path.join(config.LEARNING_DATA_DIR, "emotion_intervention_logs.json")
_lock = threading.Lock()


def _load() -> list:
    if not os.path.exists(_LOG_PATH):
        return []
    try:
        with open(_LOG_PATH, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def append_log(entry: dict) -> dict:
    with _lock:
        logs = _load()
        logs.append(entry)
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    return entry


def get_logs(limit: int = 200) -> list:
    with _lock:
        logs = _load()
    return logs[-limit:]


def clear_logs() -> int:
    with _lock:
        count = len(_load())
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
    return count
