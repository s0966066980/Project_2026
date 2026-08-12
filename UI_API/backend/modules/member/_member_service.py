import csv
import hashlib
import hmac
import io
import re
import threading
from datetime import datetime, timedelta
from itertools import combinations
from uuid import UUID, uuid4

import config
from capabilities import catalog

# Recommendation events belong to another capability; they are read through its
# published surface rather than by reaching for its table.
from capabilities.recommendation_analytics import recommendation_event_repository
from models.commercial_scope import CommercialScope
from modules.member._pii import configured_key_provider, phone_lookup_hash, protect_phone
from modules.member.adapters import member as member_repository
from modules.member.adapters import sessions as member_session_repository

_session_member: dict[str, str] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _retention_until(now: datetime | None = None) -> str:
    base = now or datetime.now()
    try:
        days = max(1, int(config.get("MEMBER_DATA_RETENTION_DAYS", 730)))
    except Exception:
        days = 730
    return (base + timedelta(days=days)).isoformat()


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y", "同意")


def _with_member_commercial_defaults(member: dict | None) -> dict | None:
    if not isinstance(member, dict):
        return member
    member.setdefault("created_at", _now_iso())
    member.setdefault("consent_version", "")
    member.setdefault("privacy_version", "")
    member.setdefault("consent_accepted_at", "")
    member.setdefault("consent_source", "")
    member.setdefault("order_history_consent", False)
    member.setdefault("personalization_consent", False)
    member.setdefault("last_login_at", "")
    member.setdefault("login_count", 0)
    member.setdefault("login_failed_count", 0)
    member.setdefault("data_retention_until", _retention_until())
    member.setdefault("deleted_at", "")
    return member


def _apply_consent_fields(
    member: dict,
    *,
    order_history_consent: bool,
    personalization_consent: bool,
    source: str = "kiosk",
) -> dict:
    member["order_history_consent"] = _as_bool(order_history_consent)
    member["personalization_consent"] = _as_bool(personalization_consent)
    member["consent_version"] = str(config.get("MEMBER_CONSENT_VERSION", "2026-07-phone-login-v1"))
    member["privacy_version"] = str(config.get("MEMBER_PRIVACY_VERSION", "2026-07-privacy-v1"))
    member["consent_accepted_at"] = _now_iso()
    member["consent_source"] = str(source or "kiosk")
    member["data_retention_until"] = _retention_until()
    return member


def _mark_login_success(member: dict) -> dict:
    _with_member_commercial_defaults(member)
    member["last_login_at"] = _now_iso()
    member["login_count"] = int(member.get("login_count", 0) or 0) + 1
    member["login_failed_count"] = 0
    return member


def normalize_phone(raw) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits if len(digits) == 10 else ""


def mask_phone(phone) -> str:
    p = str(phone or "")
    if len(p) != 10:
        return p
    return f"{p[:4]}-***-{p[7:]}"


def _member_ref(phone) -> str:
    secret = str(config.get("ADMIN_MEMBER_REF_SECRET", "local-admin-member-ref") or "local-admin-member-ref")
    value = str(phone or "")
    digest = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"mem_{digest[:24]}"


def _identity_mode() -> str:
    return str(config.MEMBER_IDENTITY_READ_MODE or "legacy").lower()


def _prepare_member_identity(record: dict, scope: CommercialScope | None) -> dict:
    prepared = dict(record)
    member_id = str(prepared.get("member_id") or prepared.get("id") or uuid4())
    prepared["id"] = member_id
    prepared["member_id"] = member_id
    if scope and (config.MEMBER_IDENTITY_DUAL_WRITE or _identity_mode() != "legacy"):
        protected = protect_phone(str(prepared.get("phone") or ""), scope.tenant_id, configured_key_provider())
        prepared.update(
            {
                "phone_lookup_hash": protected.phone_lookup_hash,
                "phone_encrypted": protected.phone_encrypted,
                "phone_masked": protected.phone_masked,
                "key_version": protected.key_version,
                "pii_updated_at": _now_iso(),
            }
        )
    return prepared


def _get_member_for_phone(phone: str, scope: CommercialScope | None) -> dict | None:
    if not scope or _identity_mode() == "legacy":
        return member_repository.get_member_scoped(phone, scope) if scope else member_repository.get_member(phone)
    lookup_hash = phone_lookup_hash(phone, scope.tenant_id, configured_key_provider())
    member = member_repository.get_member_by_lookup_hash_scoped(lookup_hash, scope)
    if member or _identity_mode() == "uuid_only":
        return member
    return member_repository.get_member_by_phone_scoped(phone, scope)


def _resolve_member(identifier, scope: CommercialScope | None = None) -> dict | None:
    raw = str(identifier or "")
    normalized = normalize_phone(raw) or raw
    member = _get_member_for_phone(normalized, scope)
    if member:
        return _with_member_commercial_defaults(member)
    if raw.startswith("mem_"):
        rows = member_repository.get_all_members_scoped(scope) if scope else member_repository.get_all_members()
        for row in rows:
            if _member_ref(row.get("member_id") or row.get("id") or row.get("phone", "")) == raw:
                return _with_member_commercial_defaults(row)
    return None


def _admin_member_identity(member: dict) -> dict:
    member_id = str(member.get("member_id") or member.get("id") or "")
    return {
        "member_id": member_id,
        "member_ref": _member_ref(member_id or member.get("phone", "")),
        "phone_masked": str(member.get("phone_masked") or mask_phone(member.get("phone", ""))),
    }


def _session_cache_key(session_id: str, scope: CommercialScope | None) -> str:
    return f"{scope.tenant_id}:{scope.store_id}:{session_id}" if scope else session_id


def bind_session(session_id: str, phone: str, scope: CommercialScope | None = None) -> None:
    cache_key = _session_cache_key(session_id, scope)
    with _lock:
        _session_member[cache_key] = phone
    if scope:
        member_session_repository.bind_session_scoped(session_id, phone, scope)
        return
    try:
        member_session_repository.bind_session(session_id, phone)
    except Exception:
        pass


def clear_session(session_id: str, scope: CommercialScope | None = None) -> None:
    cache_key = _session_cache_key(session_id, scope)
    with _lock:
        _session_member.pop(cache_key, None)
    if scope:
        member_session_repository.clear_session_scoped(session_id, scope)
        return
    try:
        member_session_repository.clear_session(session_id)
    except Exception:
        pass


def get_session_member(session_id: str, scope: CommercialScope | None = None) -> dict | None:
    cache_key = _session_cache_key(session_id, scope)
    with _lock:
        phone = _session_member.get(cache_key)
    if not phone:
        if scope:
            phone = member_session_repository.get_session_phone_scoped(session_id, scope)
        else:
            try:
                phone = member_session_repository.get_session_phone(session_id)
            except Exception:
                phone = ""
        if phone:
            with _lock:
                _session_member[cache_key] = phone
    if not phone:
        return None
    member = member_repository.get_member_scoped(phone, scope) if scope else member_repository.get_member(phone)
    return _with_member_commercial_defaults(member)


def _public_member(member: dict) -> dict:
    _with_member_commercial_defaults(member)
    return {
        "member_id": str(member.get("member_id") or member.get("id") or ""),
        "phone": member.get("phone", ""),
        "phone_masked": mask_phone(member.get("phone", "")),
        "nickname": member.get("nickname", ""),
        "visit_count": int(member.get("visit_count", 0)),
        "consent_version": member.get("consent_version", ""),
        "privacy_version": member.get("privacy_version", ""),
        "order_history_consent": bool(member.get("order_history_consent", False)),
        "personalization_consent": bool(member.get("personalization_consent", False)),
        "usuals": build_usuals(member),
        "history": build_history(member),
    }


def _menu_by_id() -> dict:
    return {str(i["id"]): i for i in catalog.list_active_items() if i.get("id")}


def _as_positive_int(value, default: int = 1, maximum: int = 20) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(1, min(maximum, parsed))


def _counter_add(counter: dict, key: str, amount: int = 1) -> dict:
    if not key:
        return counter
    counter[key] = int(counter.get(key, 0) or 0) + max(1, amount)
    return counter


def _normalize_pair_key(first_item_id: str, second_item_id: str) -> str:
    first = str(first_item_id or "").strip()
    second = str(second_item_id or "").strip()
    if not first or not second or first == second:
        return ""
    return "|".join(sorted([first, second]))


def _recent_item_ids(existing: list, ordered_item_ids: list[str], limit: int | None = None) -> list[str]:
    if limit is None:
        limit = int(config.get("MEMBER_RECENT_ITEMS_KEEP", 20))
    rows = []
    seen = set()
    for value in list(ordered_item_ids or []) + list(existing or []):
        item_id = str(value or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        rows.append(item_id)
        if len(rows) >= limit:
            break
    return rows


def login(session_id: str, phone: str, scope: CommercialScope | None = None) -> dict:
    norm = normalize_phone(phone)
    if not norm:
        return {"found": False, "error": "invalid_phone"}
    member = _get_member_for_phone(norm, scope)
    if not member:
        return {"found": False}
    _mark_login_success(member)
    member = _prepare_member_identity(member, scope)
    member_repository.upsert_member_scoped(member, scope) if scope else member_repository.upsert_member(member)
    bind_session(session_id, norm, scope)
    return {"found": True, "member": _public_member(member)}


def register(
    session_id: str,
    phone: str,
    nickname: str = "",
    order_history_consent: bool = True,
    personalization_consent: bool = True,
    consent_source: str = "kiosk",
    scope: CommercialScope | None = None,
    necessary_terms_accepted: bool = True,
) -> dict:
    norm = normalize_phone(phone)
    if not norm:
        return {"ok": False, "error": "invalid_phone"}
    order_history_consent = _as_bool(order_history_consent)
    personalization_consent = _as_bool(personalization_consent)
    if not _as_bool(necessary_terms_accepted):
        return {"ok": False, "error": "consent_required"}
    existing = _get_member_for_phone(norm, scope)
    if existing:
        _with_member_commercial_defaults(existing)
        if not existing.get("consent_accepted_at"):
            _apply_consent_fields(
                existing,
                order_history_consent=order_history_consent,
                personalization_consent=personalization_consent,
                source=consent_source,
            )
        _mark_login_success(existing)
        existing = _prepare_member_identity(existing, scope)
        member_repository.upsert_member_scoped(existing, scope) if scope else member_repository.upsert_member(existing)
        bind_session(session_id, norm, scope)
        return {"ok": True, "member": _public_member(existing)}
    nick = str(nickname or "").strip() or f"會員{norm[-4:]}"
    now = _now_iso()
    record = {
        "id": str(uuid4()),
        "phone": norm,
        "nickname": nick,
        "created_at": now,
        "visit_count": 0,
        "total_spend": 0,
        "last_visit_at": "",
        "item_freq": {},
        "category_freq": {},
        "pair_freq": {},
        "recent_item_ids": [],
        "preference_updated_at": "",
        "last_login_at": now,
        "login_count": 1,
        "login_failed_count": 0,
        "deleted_at": "",
        "orders": [],
    }
    _apply_consent_fields(
        record,
        order_history_consent=order_history_consent,
        personalization_consent=personalization_consent,
        source=consent_source,
    )
    record = _prepare_member_identity(record, scope)
    member_repository.upsert_member_scoped(record, scope) if scope else member_repository.upsert_member(record)
    bind_session(session_id, norm, scope)
    return {"ok": True, "member": _public_member(record)}


def build_usuals(member: dict, limit: int | None = None) -> list:
    if limit is None:
        limit = int(config.get("MEMBER_USUALS_COUNT", 8))
    freq = member.get("item_freq") or {}
    if not freq:
        return []
    menu_by_id = _menu_by_id()
    usuals = []
    for iid, count in sorted(freq.items(), key=lambda kv: kv[1], reverse=True):
        item = menu_by_id.get(iid)
        if not item:
            continue
        usuals.append(
            {
                "id": iid,
                "name": item.get("name", ""),
                "price": item.get("price", 0),
                "image": item.get("official_image_url") or item.get("image", ""),
                "category": item.get("category", ""),
                "count": count,
            }
        )
        if len(usuals) >= limit:
            break
    return usuals


def build_history(member: dict, limit: int | None = None) -> list:
    if limit is None:
        limit = int(config.get("MEMBER_ORDERS_KEEP", 20))
    orders = member.get("orders") or []
    if not orders:
        return []
    menu_by_id = _menu_by_id()
    history = []
    for order in reversed(orders):  # 最新在前
        counts = {}
        for iid in order.get("cart_ids") or []:
            if iid:
                counts[iid] = counts.get(iid, 0) + 1
        items = [
            {
                "id": iid,
                "name": menu_by_id.get(iid, {}).get("name", iid),
                "price": menu_by_id.get(iid, {}).get("price", 0),
                "count": cnt,
            }
            for iid, cnt in counts.items()
        ]
        history.append(
            {
                "timestamp": order.get("timestamp", ""),
                "total": int(order.get("total", 0)),
                "is_success": bool(order.get("recommendation_success", order.get("is_success", True))),
                "recommendation_success": bool(order.get("recommendation_success", order.get("is_success", True))),
                "order_status": order.get("order_status", "completed"),
                "is_completed": bool(order.get("is_completed", True)),
                "cancel_reason": order.get("cancel_reason", ""),
                "items": items,
            }
        )
        if len(history) >= limit:
            break
    return history


def _order_is_completed(order: dict) -> bool:
    if isinstance(order.get("order_status"), str) and order.get("order_status"):
        return order.get("order_status") == "completed"
    if isinstance(order.get("is_completed"), bool):
        return bool(order.get("is_completed"))
    return True


def _order_recommendation_success(order: dict) -> bool:
    return bool(order.get("recommendation_success", order.get("is_success", False)))


def _order_item_rows(order: dict, menu_by_id: dict) -> list:
    counts = {}
    for iid in order.get("cart_ids") or []:
        if iid:
            counts[iid] = counts.get(iid, 0) + 1
    return [
        {
            "id": iid,
            "name": menu_by_id.get(iid, {}).get("name", iid),
            "price": menu_by_id.get(iid, {}).get("price", 0),
            "count": cnt,
        }
        for iid, cnt in counts.items()
    ]


def _member_order_metrics(member: dict) -> dict:
    orders = list(member.get("orders") or [])
    completed_orders = [o for o in orders if _order_is_completed(o)]
    incomplete_orders = [o for o in orders if not _order_is_completed(o)]
    completed_spend = sum(int(o.get("total", 0) or 0) for o in completed_orders)
    recommendation_hit_count = sum(1 for o in completed_orders if _order_recommendation_success(o))
    completed_count = len(completed_orders)
    total_count = len(orders)
    return {
        "order_count": total_count,
        "completed_order_count": completed_count,
        "incomplete_order_count": len(incomplete_orders),
        "completed_spend": completed_spend,
        "avg_completed_spend": completed_spend // completed_count if completed_count else 0,
        "recommendation_hit_count": recommendation_hit_count,
        "recommendation_hit_rate": round(recommendation_hit_count / completed_count, 3) if completed_count else 0,
        "incomplete_rate": round(len(incomplete_orders) / total_count, 3) if total_count else 0,
        "last_order_status": (
            "completed" if _order_is_completed(orders[-1]) else orders[-1].get("order_status", "cancelled")
        )
        if orders
        else "",
    }


def _member_recommendation_summary(member: dict) -> dict:
    phone_masked = mask_phone(member.get("phone", ""))
    if not phone_masked:
        return {
            "shown": 0,
            "clicked": 0,
            "added_to_cart": 0,
            "checked_out": 0,
            "ignored": 0,
            "removed_from_cart": 0,
            "acceptance_rate": 0,
        }
    try:
        events = recommendation_event_repository.get_recommendation_events(limit=5000)
    except Exception:
        events = []
    matched = [event for event in events if str(event.get("member_phone_masked") or "") == phone_masked]
    shown = sum(1 for event in matched if event.get("event_type") == "recommendation_shown")
    checked_out = sum(1 for event in matched if event.get("event_type") == "recommendation_checked_out")
    clicked = sum(1 for event in matched if event.get("event_type") == "recommendation_clicked")
    added = sum(1 for event in matched if event.get("event_type") == "recommendation_added_to_cart")
    ignored = sum(1 for event in matched if event.get("event_type") == "recommendation_ignored")
    removed = sum(1 for event in matched if event.get("event_type") == "recommendation_removed_from_cart")
    return {
        "shown": shown,
        "clicked": clicked,
        "added_to_cart": added,
        "checked_out": checked_out,
        "ignored": ignored,
        "removed_from_cart": removed,
        "acceptance_rate": round(checked_out / shown, 3) if shown else 0,
    }


def member_top_ids(member: dict, n: int = 5) -> list:
    freq = member.get("item_freq") or {}
    return [iid for iid, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:n]]


def member_push_context(member: dict) -> str:
    usuals = build_usuals(member, limit=3)
    names = "、".join(u["name"] for u in usuals if u.get("name"))
    if not names:
        return ""
    nick = member.get("nickname", "")
    who = f"「{nick}」" if nick else ""
    return f"此顧客為會員{who}，常點：{names}。請在促購短句中自然帶入其偏好。"


def _append_member_order(member: dict, order: dict, scope: CommercialScope | None = None) -> dict:
    orders = list(member.get("orders") or [])
    orders.append(order)
    keep = int(config.get("MEMBER_ORDERS_KEEP", 20))
    member["orders"] = orders[-keep:]
    member_repository.upsert_member_scoped(member, scope) if scope else member_repository.upsert_member(member)
    return member


def _cart_item_quantities(final_cart_ids: list, cart_items: list | None = None) -> dict[str, int]:
    if isinstance(cart_items, list) and cart_items:
        quantities: dict[str, int] = {}
        for item in cart_items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                continue
            quantity = _as_positive_int(item.get("quantity", item.get("qty", 1)))
            quantities[item_id] = quantities.get(item_id, 0) + quantity
        if quantities:
            return quantities
    quantities: dict[str, int] = {}
    for iid in final_cart_ids or []:
        item_id = str(iid or "").strip()
        if item_id and item_id not in quantities:
            quantities[item_id] = 1
    return quantities


def _cart_item_rows(final_cart_ids: list, cart_items: list | None = None, menu_by_id: dict | None = None) -> list[dict]:
    menu_rows = menu_by_id if menu_by_id is not None else _menu_by_id()
    quantities = _cart_item_quantities(final_cart_ids, cart_items)
    rows = []
    for item_id, quantity in quantities.items():
        menu_item = menu_rows.get(item_id, {})
        rows.append(
            {
                "id": item_id,
                "quantity": quantity,
                "name": str(menu_item.get("name") or item_id),
                "category": str(menu_item.get("category") or ""),
            }
        )
    return rows


def _update_member_preference_stats(member: dict, cart_rows: list[dict], timestamp: str) -> None:
    item_freq = dict(member.get("item_freq") or {})
    category_freq = dict(member.get("category_freq") or {})
    pair_freq = dict(member.get("pair_freq") or {})

    ordered_item_ids = []
    for row in cart_rows:
        item_id = str(row.get("id") or "").strip()
        quantity = _as_positive_int(row.get("quantity", 1))
        if not item_id:
            continue
        ordered_item_ids.append(item_id)
        _counter_add(item_freq, item_id, quantity)
        _counter_add(category_freq, str(row.get("category") or "").strip(), quantity)

    quantity_by_id = {
        str(row.get("id") or "").strip(): _as_positive_int(row.get("quantity", 1)) for row in cart_rows if row.get("id")
    }
    for first_item_id, second_item_id in combinations(sorted(quantity_by_id), 2):
        pair_key = _normalize_pair_key(first_item_id, second_item_id)
        if not pair_key:
            continue
        pair_count = min(quantity_by_id[first_item_id], quantity_by_id[second_item_id])
        _counter_add(pair_freq, pair_key, pair_count)

    member["item_freq"] = item_freq
    member["category_freq"] = category_freq
    member["pair_freq"] = pair_freq
    member["recent_item_ids"] = _recent_item_ids(member.get("recent_item_ids") or [], ordered_item_ids)
    member["preference_updated_at"] = timestamp


def _expanded_cart_ids(final_cart_ids: list, cart_items: list | None = None) -> list[str]:
    quantities = _cart_item_quantities(final_cart_ids, cart_items)
    if not quantities:
        return list(final_cart_ids or [])
    rows = []
    for item_id, quantity in quantities.items():
        rows.extend([item_id] * quantity)
    return rows


def finalize_checkout(
    session_id: str,
    final_cart_ids: list,
    total,
    recommendation_success: bool,
    cart_items: list | None = None,
    scope: CommercialScope | None = None,
) -> dict | None:
    member = get_session_member(session_id, scope)
    if not member:
        clear_session(session_id, scope)
        return None
    timestamp = datetime.now().isoformat()
    member["visit_count"] = int(member.get("visit_count", 0)) + 1
    member["total_spend"] = int(member.get("total_spend", 0)) + int(total or 0)
    member["last_visit_at"] = timestamp
    _update_member_preference_stats(member, _cart_item_rows(final_cart_ids, cart_items), timestamp)
    _append_member_order(
        member,
        {
            "timestamp": timestamp,
            "cart_ids": _expanded_cart_ids(final_cart_ids, cart_items),
            "cart_items": cart_items if isinstance(cart_items, list) else [],
            "total": int(total or 0),
            "order_status": "completed",
            "is_completed": True,
            "recommendation_success": bool(recommendation_success),
            # Backward-compatible field for admin recommendation metrics.
            "is_success": bool(recommendation_success),
        },
        scope,
    )
    clear_session(session_id, scope)
    return member


def record_abandoned_order(
    session_id: str,
    cart_ids: list,
    total,
    reason: str = "",
    scope: CommercialScope | None = None,
) -> dict | None:
    member = get_session_member(session_id, scope)
    normalized_cart_ids = [iid for iid in (cart_ids or []) if iid]
    if not member or not normalized_cart_ids:
        return None
    member["last_visit_at"] = datetime.now().isoformat()
    _append_member_order(
        member,
        {
            "timestamp": datetime.now().isoformat(),
            "cart_ids": normalized_cart_ids,
            "total": int(total or 0),
            "order_status": "cancelled",
            "is_completed": False,
            "cancel_reason": str(reason or ""),
            "recommendation_success": False,
            "is_success": False,
        },
        scope,
    )
    clear_session(session_id, scope)
    return member


def admin_list(scope: CommercialScope | None = None) -> list:
    members = member_repository.get_all_members_scoped(scope) if scope else member_repository.get_all_members()
    menu_by_id = _menu_by_id()
    rows = []
    for m in members:
        _with_member_commercial_defaults(m)
        favs = [menu_by_id.get(iid, {}).get("name", iid) for iid in member_top_ids(m, 2)]
        metrics = _member_order_metrics(m)
        rows.append(
            {
                **_admin_member_identity(m),
                "nickname": m.get("nickname", ""),
                "visit_count": int(m.get("visit_count", 0)),
                "total_spend": int(m.get("total_spend", 0)),
                "last_visit_at": m.get("last_visit_at", ""),
                "last_login_at": m.get("last_login_at", ""),
                "login_count": int(m.get("login_count", 0) or 0),
                "consent_version": m.get("consent_version", ""),
                "privacy_version": m.get("privacy_version", ""),
                "consent_accepted_at": m.get("consent_accepted_at", ""),
                "order_history_consent": bool(m.get("order_history_consent", False)),
                "personalization_consent": bool(m.get("personalization_consent", False)),
                "data_retention_until": m.get("data_retention_until", ""),
                "favorites": favs,
                **metrics,
            }
        )
    return rows


def admin_search(
    query: str = "",
    *,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    scope: CommercialScope | None = None,
) -> tuple[list[dict], int]:
    """Search and page masked Admin member summaries behind one interface."""

    rows = admin_list(scope)
    needle = str(query or "").strip().casefold()
    if needle:
        rows = [
            row
            for row in rows
            if needle
            in " ".join(
                str(row.get(key) or "").casefold() for key in ("member_id", "member_ref", "nickname", "phone_masked")
            )
        ]
    allowed_sort = {"created_at", "nickname", "visit_count", "total_spend"}
    resolved_sort = sort_by if sort_by in allowed_sort else "created_at"
    rows.sort(
        key=lambda row: (row.get(resolved_sort) is not None, row.get(resolved_sort) or ""),
        reverse=sort_order != "asc",
    )
    total = len(rows)
    safe_page_size = max(1, min(int(page_size), 100))
    offset = (max(1, int(page)) - 1) * safe_page_size
    return rows[offset : offset + safe_page_size], total


def admin_detail(phone, scope: CommercialScope | None = None) -> dict | None:
    m = _resolve_member(phone, scope)
    if not m:
        return None
    menu_by_id = _menu_by_id()
    freq = m.get("item_freq") or {}
    ranked = [
        {"id": iid, "name": menu_by_id.get(iid, {}).get("name", iid), "count": cnt}
        for iid, cnt in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    ]
    categories_ranked = [
        {"category": category, "count": cnt}
        for category, cnt in sorted((m.get("category_freq") or {}).items(), key=lambda kv: kv[1], reverse=True)
        if category
    ]
    pairs_ranked = []
    for pair_key, count in sorted((m.get("pair_freq") or {}).items(), key=lambda kv: kv[1], reverse=True):
        item_ids = [part for part in str(pair_key).split("|") if part]
        if len(item_ids) != 2:
            continue
        pairs_ranked.append(
            {
                "item_ids": item_ids,
                "names": [menu_by_id.get(item_id, {}).get("name", item_id) for item_id in item_ids],
                "count": count,
            }
        )
    visit = int(m.get("visit_count", 0))
    spend = int(m.get("total_spend", 0))
    metrics = _member_order_metrics(m)
    orders = []
    for order in reversed(m.get("orders") or []):
        completed = _order_is_completed(order)
        orders.append(
            {
                "timestamp": order.get("timestamp", ""),
                "cart_ids": list(order.get("cart_ids") or []),
                "items": _order_item_rows(order, menu_by_id),
                "total": int(order.get("total", 0) or 0),
                "order_status": order.get("order_status", "completed" if completed else "cancelled"),
                "is_completed": completed,
                "cancel_reason": order.get("cancel_reason", ""),
                "recommendation_success": _order_recommendation_success(order),
                "is_success": _order_recommendation_success(order),
            }
        )
    return {
        **_admin_member_identity(m),
        "nickname": m.get("nickname", ""),
        "created_at": m.get("created_at", ""),
        "last_login_at": m.get("last_login_at", ""),
        "login_count": int(m.get("login_count", 0) or 0),
        "login_failed_count": int(m.get("login_failed_count", 0) or 0),
        "consent_version": m.get("consent_version", ""),
        "privacy_version": m.get("privacy_version", ""),
        "consent_accepted_at": m.get("consent_accepted_at", ""),
        "consent_source": m.get("consent_source", ""),
        "order_history_consent": bool(m.get("order_history_consent", False)),
        "personalization_consent": bool(m.get("personalization_consent", False)),
        "data_retention_until": m.get("data_retention_until", ""),
        "deleted_at": m.get("deleted_at", ""),
        "visit_count": visit,
        "total_spend": spend,
        "avg_spend": (spend // visit if visit else 0),
        "last_visit_at": m.get("last_visit_at", ""),
        "favorites_ranked": ranked,
        "categories_ranked": categories_ranked,
        "pairs_ranked": pairs_ranked,
        "recent_item_ids": list(m.get("recent_item_ids") or []),
        "preference_updated_at": m.get("preference_updated_at", ""),
        "verified_preferences": dict(m.get("verified_preferences") or {}),
        "inferred_preferences": {
            "favorite_items": ranked,
            "categories": categories_ranked,
            "pairs": pairs_ranked,
            "source": "completed_order_history",
            "updated_at": m.get("preference_updated_at", ""),
        },
        "recommendation_summary": _member_recommendation_summary(m),
        "orders": orders,
        **metrics,
    }


def export_members_csv(scope: CommercialScope | None = None) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "phone_masked",
            "nickname",
            "consent_version",
            "consent_accepted_at",
            "order_history_consent",
            "personalization_consent",
            "data_retention_until",
            "last_login_at",
            "visit_count",
            "completed_order_count",
            "incomplete_order_count",
            "completed_spend",
            "avg_completed_spend",
            "last_visit_at",
            "favorites",
            "preferred_categories",
        ],
    )
    writer.writeheader()
    menu_by_id = _menu_by_id()
    members = member_repository.get_all_members_scoped(scope) if scope else member_repository.get_all_members()
    for member in members:
        _with_member_commercial_defaults(member)
        metrics = _member_order_metrics(member)
        usuals = build_usuals(member, limit=5)
        categories = [
            category
            for category, _ in sorted(
                (member.get("category_freq") or {}).items(),
                key=lambda item: int(item[1] or 0),
                reverse=True,
            )
            if category
        ][:5]
        if not categories:
            categories = [
                str(menu_by_id.get(item.get("id"), {}).get("category") or "") for item in usuals if item.get("id")
            ][:5]
        writer.writerow(
            {
                "phone_masked": str(member.get("phone_masked") or mask_phone(member.get("phone", ""))),
                "nickname": member.get("nickname", ""),
                "consent_version": member.get("consent_version", ""),
                "consent_accepted_at": member.get("consent_accepted_at", ""),
                "order_history_consent": bool(member.get("order_history_consent", False)),
                "personalization_consent": bool(member.get("personalization_consent", False)),
                "data_retention_until": member.get("data_retention_until", ""),
                "last_login_at": member.get("last_login_at", ""),
                "visit_count": int(member.get("visit_count", 0) or 0),
                "completed_order_count": metrics.get("completed_order_count", 0),
                "incomplete_order_count": metrics.get("incomplete_order_count", 0),
                "completed_spend": metrics.get("completed_spend", 0),
                "avg_completed_spend": metrics.get("avg_completed_spend", 0),
                "last_visit_at": member.get("last_visit_at", ""),
                "favorites": "、".join(item.get("name", "") for item in usuals if item.get("name")),
                "preferred_categories": "、".join(category for category in categories if category),
            }
        )
    return output.getvalue()


def admin_update_verified_preferences(
    identifier,
    preferences: dict,
    *,
    actor_id: str = "",
    scope: CommercialScope | None = None,
) -> dict | None:
    member = _resolve_member(identifier, scope)
    if not member:
        return None

    def string_list(key: str, limit: int = 10) -> list[str]:
        values = preferences.get(key) or []
        if not isinstance(values, list):
            raise ValueError(f"{key} must be a list")
        normalized = []
        for value in values:
            text = str(value or "").strip()[:80]
            if text and text not in normalized:
                normalized.append(text)
        return normalized[:limit]

    verified = {
        "allergies": string_list("allergies"),
        "dietary_preferences": string_list("dietary_preferences"),
        "favorite_item_ids": string_list("favorite_item_ids", 20),
        "service_notes": str(preferences.get("service_notes") or "").strip()[:500],
        "source": "member_confirmed",
        "verified_at": datetime.now().isoformat(),
        "verified_by": str(actor_id or ""),
    }
    member["verified_preferences"] = verified
    if scope:
        member_repository.upsert_member_scoped(member, scope)
    else:
        member_repository.upsert_member(member)
    return verified


def admin_clear_records(phone, scope: CommercialScope | None = None) -> bool:
    """清除會員的點餐紀錄（訂單、常點、消費統計），保留帳戶本身。"""
    m = _resolve_member(phone, scope)
    if not m:
        return False
    m["orders"] = []
    m["item_freq"] = {}
    m["category_freq"] = {}
    m["pair_freq"] = {}
    m["recent_item_ids"] = []
    m["preference_updated_at"] = ""
    m["visit_count"] = 0
    m["total_spend"] = 0
    m["last_visit_at"] = ""
    member_repository.upsert_member_scoped(m, scope) if scope else member_repository.upsert_member(m)
    return True


def admin_delete_member(phone, scope: CommercialScope | None = None) -> bool:
    """刪除會員；UUID PostgreSQL 路徑先去識別化並保留生命週期證據。"""
    m = _resolve_member(phone, scope)
    if not m:
        return False
    member_id = str(m.get("member_id") or m.get("id") or "")
    if scope and member_id and _identity_mode() != "legacy":
        return member_repository.anonymize_member_by_id_scoped(UUID(member_id), scope)
    if scope:
        return member_repository.delete_member_scoped(m.get("phone", ""), scope)
    return member_repository.delete_member(m.get("phone", ""))
