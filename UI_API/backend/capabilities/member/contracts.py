"""Published Member vocabulary; no ordering transaction state is exposed."""

from __future__ import annotations

from typing import Any, TypedDict


class MemberView(TypedDict, total=False):
    member_ref: str
    status: str
    consent_version: str
    preferences: dict[str, Any]
    history: list[dict[str, Any]]


class MemberCapabilityError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
