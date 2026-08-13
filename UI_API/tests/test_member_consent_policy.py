"""Optional Member consents must independently control optional data surfaces."""

import pytest

from capabilities.member import member_service
from modules.member import member_service as member_internals

pytestmark = [pytest.mark.unit, pytest.mark.security]


def _member(**overrides):
    return {
        "id": "member-1",
        "phone": "0912345678",
        "nickname": "Test",
        "item_freq": {"coffee": 2},
        "orders": [{"cart_ids": ["coffee"], "total": 50}],
        "order_history_consent": False,
        "personalization_consent": False,
        **overrides,
    }


def test_necessary_terms_are_required_but_optional_consents_are_independent():
    result = member_service.register(
        "consent-required",
        "0912345678",
        order_history_consent=False,
        personalization_consent=False,
        necessary_terms_accepted=False,
    )

    assert result == {"ok": False, "error": "consent_required"}


def test_without_optional_consent_public_member_has_no_history_or_personalization(monkeypatch):
    monkeypatch.setattr(member_internals, "_menu_by_id", lambda: {"coffee": {"name": "Coffee", "price": 50}})

    view = member_service.public_member(_member())

    assert view["history"] == []
    assert view["usuals"] == []
    assert member_internals.member_push_context(_member()) == ""


def test_optional_consents_reenable_only_their_own_surface(monkeypatch):
    monkeypatch.setattr(member_internals, "_menu_by_id", lambda: {"coffee": {"name": "Coffee", "price": 50}})

    history_only = member_service.public_member(_member(order_history_consent=True))
    personalization_only = member_service.public_member(_member(personalization_consent=True))

    assert len(history_only["history"]) == 1
    assert history_only["usuals"] == []
    assert personalization_only["history"] == []
    assert personalization_only["usuals"][0]["id"] == "coffee"
