"""Published Member operations; Guest ordering does not require this surface."""

from __future__ import annotations

from typing import Any

from capabilities.member.contracts import MemberCapabilityError, MemberView


def login(session_id: str, phone: str, scope: Any = None) -> dict[str, Any]:
    from services import member_service

    return member_service.login(session_id, phone, scope)


def register(session_id: str, phone: str, *, scope: Any = None, **values: Any) -> dict[str, Any]:
    from services import member_service

    return member_service.register(session_id, phone, scope=scope, **values)


def get_session_member(session_id: str, scope: Any = None) -> MemberView | None:
    from services import member_service

    return member_service.get_session_member(session_id, scope)  # type: ignore[return-value]


def normalize_phone(value: Any) -> str:
    from services import member_service

    return member_service.normalize_phone(value)


def mask_phone(value: Any) -> str:
    from services import member_service

    return member_service.mask_phone(value)


def public_member(value: dict[str, Any] | None) -> dict[str, Any] | None:
    from services import member_service

    return member_service._public_member(value) if value else None


def _forward(name: str, *args: Any, **kwargs: Any) -> Any:
    from services import member_service

    return getattr(member_service, name)(*args, **kwargs)


def admin_clear_records(*args: Any, **kwargs: Any) -> Any:
    return _forward("admin_clear_records", *args, **kwargs)


def admin_delete_member(*args: Any, **kwargs: Any) -> Any:
    return _forward("admin_delete_member", *args, **kwargs)


def admin_detail(*args: Any, **kwargs: Any) -> Any:
    return _forward("admin_detail", *args, **kwargs)


def admin_list(*args: Any, **kwargs: Any) -> Any:
    return _forward("admin_list", *args, **kwargs)


def admin_search(*args: Any, **kwargs: Any) -> Any:
    return _forward("admin_search", *args, **kwargs)


def admin_update_verified_preferences(*args: Any, **kwargs: Any) -> Any:
    return _forward("admin_update_verified_preferences", *args, **kwargs)


def export_members_csv(*args: Any, **kwargs: Any) -> Any:
    return _forward("export_members_csv", *args, **kwargs)


def record_abandoned_order(*args: Any, **kwargs: Any) -> Any:
    return _forward("record_abandoned_order", *args, **kwargs)


def __getattr__(name: str):
    """Expose the remaining versioned Member application calls lazily."""

    if name in {
        "admin_clear_records",
        "admin_delete_member",
        "admin_detail",
        "admin_list",
        "admin_search",
        "admin_update_verified_preferences",
        "export_members_csv",
        "record_abandoned_order",
    }:
        from services import member_service

        return getattr(member_service, name)
    raise AttributeError(name)


class _MemberServiceProxy:
    def __getattr__(self, name: str):
        if name == "_public_member":
            return public_member
        return globals()[name]


member_service = _MemberServiceProxy()


__all__ = [
    "MemberCapabilityError",
    "MemberView",
    "admin_clear_records",
    "admin_delete_member",
    "admin_detail",
    "admin_list",
    "admin_search",
    "admin_update_verified_preferences",
    "export_members_csv",
    "get_session_member",
    "login",
    "mask_phone",
    "member_service",
    "normalize_phone",
    "public_member",
    "record_abandoned_order",
    "register",
]
