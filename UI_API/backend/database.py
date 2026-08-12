from capabilities import catalog
from modules.operations.adapters import logs as log_repository
from modules.recommendation import _service as recommendation_service


def build_menu_item_text(item: dict) -> str:
    prep_minutes = item.get("prep_time_minutes", item.get("prep_minutes", ""))
    return (
        f"ID: {item.get('id')}\n"
        f"名稱: {item.get('name')}\n"
        f"描述: {item.get('description')}\n"
        f"營養: {item.get('nutrition', '')}\n"
        f"製作時間: {prep_minutes}分鐘\n"
        f"價格: {item.get('price')}元"
    )


def build_full_menu_context() -> str:
    menu_items = catalog.list_active_items()
    if not menu_items:
        return "【完整菜單白名單】目前沒有菜單資料。"
    lines = ["【完整菜單白名單】", "只能使用以下餐點 ID 與名稱，不得創造其他餐點。"]
    for item in menu_items:
        lines.append(build_menu_item_text(item))
    return "\n\n".join(lines)


def build_compact_menu_context() -> str:
    """精簡版菜單 context（語音模式專用）。
    格式：ID｜名稱｜分類｜價格  一行一道菜，token 數約為完整版的 1/10。
    LLM 仍可依 ID 加購、回答名稱與價格，製作時間等細節移除。
    """
    menu_items = catalog.list_active_items()
    if not menu_items:
        return "【菜單白名單】目前沒有菜單資料。"
    rows = ["【菜單白名單】ID｜名稱｜分類｜價格"]
    for item in menu_items:
        iid = item.get("id", "")
        name = item.get("name", "")
        cat = item.get("category", "")
        price = item.get("price", "")
        rows.append(f"{iid}｜{name}｜{cat}｜${price}")
    return "\n".join(rows)


# `update_menu` used to bulk-replace the store catalog master from here. It had
# no callers — the Admin bulk replace goes through `menu_catalog_service` — and
# a second, unreachable writer is exactly what a data-authority statement has to
# exclude to mean anything. Removed with the catalog capability's read
# interface; the surviving writer is `services/menu_catalog_service.py`.


def record_final_checkout(
    session_id: str,
    pushed_ids: list,
    cart_ids: list,
    cart_items: list | None,
    session_history: list,
    ai_push_cart_count: int = 0,
    cart_sources: list | None = None,
) -> dict:
    log_entry = recommendation_service.build_checkout_log_entry(
        session_id=session_id,
        pushed_ids=pushed_ids,
        cart_ids=cart_ids,
        cart_items=cart_items if isinstance(cart_items, list) else [],
        session_history=session_history,
    )
    log_entry["ai_push_cart_count"] = max(0, int(ai_push_cart_count))
    log_entry["ai_push_success"] = ai_push_cart_count >= 1
    log_entry["cart_sources"] = cart_sources if isinstance(cart_sources, list) else []
    return log_repository.append_session_log(log_entry)
