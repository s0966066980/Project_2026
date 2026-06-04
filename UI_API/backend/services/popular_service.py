"""熱門餐點服務 — 從 session logs 統計點選頻率，回傳 TOP N。"""
import threading
import time

from repositories import log_repository, menu_repository

_cache: dict = {"top": [], "ts": 0.0}
_cache_lock = threading.Lock()
_CACHE_TTL = 60.0


def get_top_items(n: int = 3) -> list[dict]:
    """回傳點選頻率前 n 名的餐點，格式：[{id, name, count}, ...]。"""
    now = time.monotonic()
    with _cache_lock:
        if _cache["top"] and now - _cache["ts"] < _CACHE_TTL:
            return _cache["top"][:n]

    logs = log_repository.get_session_logs()
    freq: dict[str, int] = {}
    for log in logs:
        for item_id in (log.get("final_cart_ids") or []):
            if item_id:
                freq[item_id] = freq.get(item_id, 0) + 1

    menu_by_id = {i["id"]: i for i in menu_repository.get_menu() if i.get("id")}
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    top = [
        {"id": iid, "name": menu_by_id[iid].get("name", iid), "count": cnt}
        for iid, cnt in ranked
        if iid in menu_by_id
    ]

    with _cache_lock:
        _cache["top"] = top
        _cache["ts"] = now

    return top[:n]
