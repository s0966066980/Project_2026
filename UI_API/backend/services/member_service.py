import re
import threading
from datetime import datetime

import config
from repositories import member_repository, menu_repository

_session_member: dict[str, str] = {}
_lock = threading.Lock()


def normalize_phone(raw) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits if len(digits) == 10 else ""


def mask_phone(phone) -> str:
    p = str(phone or "")
    if len(p) != 10:
        return p
    return f"{p[:4]}-***-{p[7:]}"


def bind_session(session_id: str, phone: str) -> None:
    with _lock:
        _session_member[session_id] = phone


def clear_session(session_id: str) -> None:
    with _lock:
        _session_member.pop(session_id, None)


def get_session_member(session_id: str) -> dict | None:
    with _lock:
        phone = _session_member.get(session_id)
    return member_repository.get_member(phone) if phone else None


def _public_member(member: dict) -> dict:
    return {
        "phone": member.get("phone", ""),
        "nickname": member.get("nickname", ""),
        "visit_count": int(member.get("visit_count", 0)),
        "usuals": build_usuals(member),
    }


def login(session_id: str, phone: str) -> dict:
    norm = normalize_phone(phone)
    if not norm:
        return {"found": False, "error": "invalid_phone"}
    member = member_repository.get_member(norm)
    if not member:
        return {"found": False}
    bind_session(session_id, norm)
    return {"found": True, "member": _public_member(member)}


def register(session_id: str, phone: str, nickname: str = "") -> dict:
    norm = normalize_phone(phone)
    if not norm:
        return {"ok": False, "error": "invalid_phone"}
    existing = member_repository.get_member(norm)
    if existing:
        bind_session(session_id, norm)
        return {"ok": True, "member": _public_member(existing)}
    nick = str(nickname or "").strip() or f"會員{norm[-4:]}"
    record = {
        "phone": norm,
        "nickname": nick,
        "created_at": datetime.now().isoformat(),
        "visit_count": 0,
        "total_spend": 0,
        "last_visit_at": "",
        "item_freq": {},
        "orders": [],
    }
    member_repository.upsert_member(record)
    bind_session(session_id, norm)
    return {"ok": True, "member": _public_member(record)}


def build_usuals(member: dict, limit: int | None = None) -> list:
    if limit is None:
        limit = int(config.get("MEMBER_USUALS_COUNT", 8))
    freq = member.get("item_freq") or {}
    if not freq:
        return []
    menu_by_id = {i["id"]: i for i in menu_repository.get_menu() if i.get("id")}
    usuals = []
    for iid, count in sorted(freq.items(), key=lambda kv: kv[1], reverse=True):
        item = menu_by_id.get(iid)
        if not item:
            continue
        usuals.append({
            "id": iid,
            "name": item.get("name", ""),
            "price": item.get("price", 0),
            "image": item.get("official_image_url") or item.get("image", ""),
            "category": item.get("category", ""),
            "count": count,
        })
        if len(usuals) >= limit:
            break
    return usuals


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


def finalize_checkout(session_id: str, final_cart_ids: list, total, is_success: bool) -> dict | None:
    member = get_session_member(session_id)
    if not member:
        clear_session(session_id)
        return None
    member["visit_count"] = int(member.get("visit_count", 0)) + 1
    member["total_spend"] = int(member.get("total_spend", 0)) + int(total or 0)
    member["last_visit_at"] = datetime.now().isoformat()
    freq = dict(member.get("item_freq") or {})
    for iid in set(final_cart_ids or []):
        if iid:
            freq[iid] = freq.get(iid, 0) + 1
    member["item_freq"] = freq
    orders = list(member.get("orders") or [])
    orders.append({
        "timestamp": datetime.now().isoformat(),
        "cart_ids": list(final_cart_ids or []),
        "total": int(total or 0),
        "is_success": bool(is_success),
    })
    keep = int(config.get("MEMBER_ORDERS_KEEP", 20))
    member["orders"] = orders[-keep:]
    member_repository.upsert_member(member)
    clear_session(session_id)
    return member


def admin_list() -> list:
    members = member_repository.get_all_members()
    menu_by_id = {i["id"]: i for i in menu_repository.get_menu() if i.get("id")}
    rows = []
    for m in members:
        favs = [menu_by_id.get(iid, {}).get("name", iid) for iid in member_top_ids(m, 2)]
        rows.append({
            "phone_masked": mask_phone(m.get("phone", "")),
            "phone": m.get("phone", ""),
            "nickname": m.get("nickname", ""),
            "visit_count": int(m.get("visit_count", 0)),
            "total_spend": int(m.get("total_spend", 0)),
            "last_visit_at": m.get("last_visit_at", ""),
            "favorites": favs,
        })
    return rows


def admin_detail(phone) -> dict | None:
    m = member_repository.get_member(normalize_phone(phone) or str(phone))
    if not m:
        return None
    menu_by_id = {i["id"]: i for i in menu_repository.get_menu() if i.get("id")}
    freq = m.get("item_freq") or {}
    ranked = [
        {"id": iid, "name": menu_by_id.get(iid, {}).get("name", iid), "count": cnt}
        for iid, cnt in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    ]
    visit = int(m.get("visit_count", 0))
    spend = int(m.get("total_spend", 0))
    return {
        "phone_masked": mask_phone(m.get("phone", "")),
        "nickname": m.get("nickname", ""),
        "created_at": m.get("created_at", ""),
        "visit_count": visit,
        "total_spend": spend,
        "avg_spend": (spend // visit if visit else 0),
        "last_visit_at": m.get("last_visit_at", ""),
        "favorites_ranked": ranked,
        "orders": list(reversed(m.get("orders") or [])),
    }
