import config
from repositories import log_repository, menu_repository
from services import recommendation_service


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
    menu_items = menu_repository.get_menu()
    if not menu_items:
        return "【完整菜單白名單】目前沒有菜單資料。"
    lines = ["【完整菜單白名單】", "只能使用以下餐點 ID 與名稱，不得創造其他餐點。"]
    for item in menu_items:
        lines.append(build_menu_item_text(item))
    return "\n\n".join(lines)


def update_menu(new_menu_data: list) -> None:
    menu_repository.save_menu(new_menu_data)
    # TODO: trigger RAG rebuild when RAG is implemented


def record_final_checkout(
    session_id: str,
    pushed_ids: list,
    cart_ids: list,
    session_history: list,
) -> dict:
    log_entry = recommendation_service.build_checkout_log_entry(
        session_id=session_id,
        pushed_ids=pushed_ids,
        cart_ids=cart_ids,
        session_history=session_history,
    )
    return log_repository.append_session_log(log_entry)
