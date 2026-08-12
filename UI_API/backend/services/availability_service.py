"""Build store availability context for recommendations and Admin."""

from datetime import datetime, time

import config
from capabilities import catalog
from models.commercial_scope import CommercialScope
from repositories import availability_repository

BREAKFAST_CATEGORY = "早餐"


def _menu_id(item: dict) -> str:
    return str(item.get("id") or "").strip()


def _valid_menu_ids(menu_items: list[dict]) -> set[str]:
    return {_menu_id(item) for item in menu_items or [] if _menu_id(item)}


def _filter_known_ids(values: list[str], valid_ids: set[str]) -> list[str]:
    rows = []
    seen = set()
    for value in values or []:
        normalized = str(value or "").strip()
        if normalized and normalized in valid_ids and normalized not in seen:
            seen.add(normalized)
            rows.append(normalized)
    return rows


def _parse_time(value: str, fallback: time) -> time:
    try:
        hour, minute = [int(part) for part in str(value or "").split(":", 1)]
        return time(hour=hour, minute=minute)
    except Exception:
        return fallback


def _is_time_between(current: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def resolve_service_period(settings: dict, now: datetime | None = None) -> str:
    configured = str(settings.get("service_period") or "auto").strip().lower()
    if configured in ("breakfast", "regular"):
        return configured

    current = (now or datetime.now()).time()
    periods = settings.get("service_periods") if isinstance(settings.get("service_periods"), dict) else {}
    breakfast = periods.get("breakfast") if isinstance(periods.get("breakfast"), dict) else {}
    start = _parse_time(breakfast.get("start", "05:00"), time(hour=5, minute=0))
    end = _parse_time(breakfast.get("end", "10:30"), time(hour=10, minute=30))
    return "breakfast" if _is_time_between(current, start, end) else "regular"


def _is_breakfast_item(item: dict) -> bool:
    category = str(item.get("category") or "").strip()
    available_categories = {
        str(category_name or "").strip()
        for category_name in item.get("available_categories") or []
        if str(category_name or "").strip()
    }
    return category == BREAKFAST_CATEGORY or BREAKFAST_CATEGORY in available_categories


def _time_unavailable_ids(menu_items: list[dict], service_period: str) -> list[str]:
    if service_period == "breakfast":
        return []
    return [_menu_id(item) for item in menu_items or [] if _menu_id(item) and _is_breakfast_item(item)]


def _availability_base(
    menu_items: list[dict],
    now: datetime | None = None,
    scope: CommercialScope | None = None,
) -> dict:
    settings = (
        availability_repository.get_availability_scoped(scope)
        if scope is not None
        else availability_repository.get_availability()
    )
    valid_ids = _valid_menu_ids(menu_items)
    service_period = resolve_service_period(settings, now=now)
    sold_out_ids = _filter_known_ids(settings.get("sold_out_item_ids", []), valid_ids)
    low_stock_ids = _filter_known_ids(settings.get("low_stock_item_ids", []), valid_ids)
    disabled_ids = _filter_known_ids(settings.get("store_disabled_item_ids", []), valid_ids)
    time_unavailable_ids = _filter_known_ids(_time_unavailable_ids(menu_items, service_period), valid_ids)
    unavailable_ids = _filter_known_ids(
        [*sold_out_ids, *disabled_ids, *time_unavailable_ids],
        valid_ids,
    )

    return {
        **settings,
        "service_period": service_period,
        "configured_service_period": settings.get("service_period", "auto"),
        "sold_out_item_ids": sold_out_ids,
        "low_stock_item_ids": low_stock_ids,
        "store_disabled_item_ids": disabled_ids,
        "time_unavailable_item_ids": time_unavailable_ids,
        "unavailable_item_ids": unavailable_ids,
        "exclude_item_ids": unavailable_ids,
        "low_stock_penalty": int(config.get("RECOMMENDATION_LOW_STOCK_PENALTY", 1) or 1),
        "generated_at": (now or datetime.now()).isoformat(timespec="seconds"),
    }


def build_availability_context(
    menu_items: list[dict] | None = None,
    now: datetime | None = None,
    scope: CommercialScope | None = None,
) -> dict:
    if not config.get("RECOMMENDATION_AVAILABILITY_ENABLED", True):
        return {
            "enabled": False,
            "exclude_item_ids": [],
            "low_stock_item_ids": [],
            "unavailable_item_ids": [],
            "low_stock_penalty": 0,
        }
    if menu_items is not None:
        rows = menu_items
    elif scope is not None:
        rows = catalog.list_items(scope, include_retired=False, ensure_seed=True)
    else:
        rows = catalog.list_active_items()
    return {"enabled": True, **_availability_base(rows, now=now, scope=scope)}


def get_admin_state(now: datetime | None = None, scope: CommercialScope | None = None) -> dict:
    if scope is not None:
        menu_items = catalog.list_items(scope, include_retired=False, ensure_seed=True)
    else:
        menu_items = catalog.list_active_items()
    context = build_availability_context(menu_items, now=now, scope=scope)
    sold_out_ids = set(context.get("sold_out_item_ids", []))
    low_stock_ids = set(context.get("low_stock_item_ids", []))
    disabled_ids = set(context.get("store_disabled_item_ids", []))
    time_unavailable_ids = set(context.get("time_unavailable_item_ids", []))
    rows = []
    for item in menu_items or []:
        item_id = _menu_id(item)
        if not item_id:
            continue
        status = "normal"
        if item_id in disabled_ids:
            status = "disabled"
        elif item_id in sold_out_ids:
            status = "sold_out"
        elif item_id in low_stock_ids:
            status = "low_stock"
        rows.append(
            {
                "id": item_id,
                "name": str(item.get("name") or item_id),
                "category": str(item.get("category") or ""),
                "price": item.get("price"),
                "description": str(item.get("description") or ""),
                "image": str(item.get("image") or ""),
                "status": status,
                "time_unavailable": item_id in time_unavailable_ids,
                "available_categories": item.get("available_categories") or [],
                "retired": bool(item.get("retired") or item.get("retired_at")),
            }
        )
    categories = sorted({str(row.get("category") or "") for row in rows if row.get("category")})
    return {**context, "items": rows, "categories": categories}


def save_admin_state(payload: dict, scope: CommercialScope | None = None) -> dict:
    if scope is not None:
        menu_items = catalog.list_items(scope, include_retired=False, ensure_seed=True)
    else:
        menu_items = catalog.list_active_items()
    valid_ids = _valid_menu_ids(menu_items)
    source = payload if isinstance(payload, dict) else {}
    row = {
        "store_id": source.get("store_id"),
        "service_period": source.get("service_period"),
        "service_periods": source.get("service_periods"),
        "sold_out_item_ids": _filter_known_ids(source.get("sold_out_item_ids", []), valid_ids),
        "low_stock_item_ids": _filter_known_ids(source.get("low_stock_item_ids", []), valid_ids),
        "store_disabled_item_ids": _filter_known_ids(source.get("store_disabled_item_ids", []), valid_ids),
    }
    if scope is None:
        availability_repository.save_availability(row)
    else:
        availability_repository.save_availability_scoped(row, scope)
    return get_admin_state(scope=scope)
