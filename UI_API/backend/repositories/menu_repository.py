import json
import os

import config


_menu_cache = None
_menu_cache_mtime = None


def get_menu() -> list:
    global _menu_cache, _menu_cache_mtime
    try:
        current_mtime = os.path.getmtime(config.MENU_JSON_PATH)
        if _menu_cache is not None and current_mtime == _menu_cache_mtime:
            return _menu_cache
        with open(config.MENU_JSON_PATH, "r", encoding="utf-8") as f:
            _menu_cache = json.load(f)
            _menu_cache_mtime = current_mtime
            return _menu_cache if isinstance(_menu_cache, list) else []
    except Exception:
        return []


def save_menu(menu_data: list) -> list:
    global _menu_cache, _menu_cache_mtime
    parent = os.path.dirname(config.MENU_JSON_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(config.MENU_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(menu_data, f, ensure_ascii=False, indent=4)
    _menu_cache = menu_data
    try:
        _menu_cache_mtime = os.path.getmtime(config.MENU_JSON_PATH)
    except OSError:
        _menu_cache_mtime = None
    return menu_data

