import json
import os
import threading

import config

SESSION_LOG_PATH = os.path.join(config.LEARNING_DATA_DIR, "session_logs.json")

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float | None, list]] = {}


def _read_list(path: str) -> list:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    with _cache_lock:
        cached = _cache.get(path)
        if cached and cached[0] == mtime:
            return list(cached[1])
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = data if isinstance(data, list) else []
    except Exception:
        return []
    with _cache_lock:
        _cache[path] = (mtime, list(result))
    return list(result)


def _write_list(path: str, rows: list) -> list:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    snapshot = list(rows)
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    with _cache_lock:
        _cache[path] = (mtime, list(snapshot))
    return snapshot


def get_session_logs() -> list:
    return _read_list(SESSION_LOG_PATH)


def save_session_logs(logs: list) -> list:
    return _write_list(SESSION_LOG_PATH, logs)


def append_session_log(log_entry: dict) -> dict:
    logs = get_session_logs()
    logs.append(log_entry)
    save_session_logs(logs)
    return log_entry


def delete_session_log(log_index: int) -> bool:
    logs = get_session_logs()
    if log_index < 0 or log_index >= len(logs):
        return False
    del logs[log_index]
    save_session_logs(logs)
    return True


def clear_session_logs() -> bool:
    save_session_logs([])
    return True
