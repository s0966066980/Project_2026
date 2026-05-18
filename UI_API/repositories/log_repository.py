import json
import os
from datetime import datetime

import config


SESSION_LOG_PATH = os.path.join(config.LEARNING_DATA_DIR, "session_logs.json")


def _read_list(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_list(path: str, rows: list) -> list:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=4)
    return rows


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


def get_rag_review_logs() -> list:
    return _read_list(config.RAG_REVIEW_LOG_PATH)


def save_rag_review_logs(logs: list) -> list:
    return _write_list(config.RAG_REVIEW_LOG_PATH, logs)


def append_rag_review_log(log_entry: dict) -> dict:
    logs = get_rag_review_logs()
    logs.append(log_entry)
    save_rag_review_logs(logs)
    return log_entry


def delete_rag_review_log(log_index: int) -> bool:
    logs = get_rag_review_logs()
    if log_index < 0 or log_index >= len(logs):
        return False
    del logs[log_index]
    save_rag_review_logs(logs)
    return True


def get_customer_service_logs() -> list:
    return _read_list(config.CUSTOMER_SERVICE_LOG_PATH)


def save_customer_service_logs(logs: list) -> list:
    return _write_list(config.CUSTOMER_SERVICE_LOG_PATH, logs)


def append_customer_service_log(log_entry: dict) -> dict:
    logs = get_customer_service_logs()
    logs.append(log_entry)
    save_customer_service_logs(logs)
    return log_entry


def update_customer_service_log(source_id: str, updates: dict, updated_at: str = "") -> dict | None:
    logs = get_customer_service_logs()
    updated = None
    for log in logs:
        if log.get("source_id") == source_id:
            log.update(updates)
            log["updated_at"] = updated_at or datetime.now().isoformat()
            updated = log
            break
    if updated:
        save_customer_service_logs(logs)
    return updated

