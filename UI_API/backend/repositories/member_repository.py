import json
import os
import threading

import config

MEMBERS_PATH = os.path.join(config.LEARNING_DATA_DIR, "members.json")

_lock = threading.Lock()


def _read() -> list:
    try:
        with open(MEMBERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(rows: list) -> list:
    parent = os.path.dirname(MEMBERS_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f"{MEMBERS_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, MEMBERS_PATH)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return rows


def get_all_members() -> list:
    with _lock:
        return _read()


def get_member(phone: str) -> dict | None:
    key = str(phone or "")
    with _lock:
        for row in _read():
            if str(row.get("phone")) == key:
                return row
    return None


def upsert_member(record: dict) -> dict:
    key = str(record.get("phone") or "")
    with _lock:
        rows = _read()
        for i, row in enumerate(rows):
            if str(row.get("phone")) == key:
                rows[i] = record
                break
        else:
            rows.append(record)
        _write(rows)
    return record


def delete_member(phone: str) -> bool:
    key = str(phone or "")
    with _lock:
        rows = _read()
        kept = [r for r in rows if str(r.get("phone")) != key]
        if len(kept) == len(rows):
            return False
        _write(kept)
    return True
