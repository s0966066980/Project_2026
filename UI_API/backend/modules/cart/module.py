from __future__ import annotations

from typing import Any, Protocol

from models.commercial_scope import CommercialScope


class CartError(RuntimeError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


class CartStore(Protocol):
    def get(self, *, scope: CommercialScope, session_id: str) -> dict[str, Any]: ...
    def replace(
        self, *, scope: CommercialScope, session_id: str, expected_revision: int, lines: list[dict[str, Any]]
    ) -> dict[str, Any]: ...
    def close(self, *, scope: CommercialScope, session_id: str, status: str) -> None: ...


class CartModule:
    def __init__(self, store: CartStore):
        self._store = store

    def get(self, *, scope: CommercialScope, session_id: str) -> dict[str, Any]:
        if not str(session_id).strip():
            raise CartError("invalid_ordering_session")
        return self._store.get(scope=scope, session_id=session_id)

    def replace(
        self, *, scope: CommercialScope, session_id: str, expected_revision: int, lines: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not isinstance(lines, list) or len(lines) > 100:
            raise CartError("invalid_cart")
        normalized = []
        for line in lines:
            item_id = str(line.get("item_id") or line.get("id") or "").strip()
            quantity = int(line.get("quantity") or 0)
            if not item_id or quantity < 1 or quantity > 99:
                raise CartError("invalid_cart_line")
            normalized.append(
                {
                    "item_id": item_id,
                    "quantity": quantity,
                    "options": list(line.get("options") or []),
                    "applied_offer_id": str(line.get("applied_offer_id") or ""),
                }
            )
        return self._store.replace(
            scope=scope,
            session_id=session_id,
            expected_revision=max(0, int(expected_revision)),
            lines=normalized,
        )

    def close(self, *, scope: CommercialScope, session_id: str, abandoned: bool = False) -> None:
        self._store.close(scope=scope, session_id=session_id, status="abandoned" if abandoned else "closed")
