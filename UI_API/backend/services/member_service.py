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
    # Task 3 取代此實作；核心任務先回空 list 以滿足 _public_member。
    return []
