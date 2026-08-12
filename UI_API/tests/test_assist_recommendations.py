import asyncio

import pytest

from services import ai_push_service

pytestmark = [pytest.mark.unit]


def test_assist_recommendations_do_not_apply_push_scope(monkeypatch):
    menu_items = [
        {
            "id": "MCD-REGULAR",
            "name": "一般時段餐點",
            "description": "適合現在享用的餐點。",
            "price": 99,
            "category": "超值全餐",
        }
    ]
    captured = {}

    async def fake_menu():
        return menu_items

    async def fake_context(session_id, **kwargs):
        captured.update(kwargs)
        return {"controls": {"surface": kwargs["surface"]}, "offers": []}

    monkeypatch.setattr(ai_push_service, "_get_menu_cached", fake_menu)

    async def fail_scope(*args):
        raise AssertionError("assist recommendations must not use push scope")

    monkeypatch.setattr(ai_push_service, "_scope_controls", fail_scope)
    monkeypatch.setattr(
        ai_push_service.push_copy_repository,
        "list_copy_scoped",
        lambda scope: {},
    )
    monkeypatch.setattr(
        ai_push_service.recommendation_context_service,
        "build_context",
        fake_context,
    )
    monkeypatch.setattr(
        ai_push_service.recommendation_experiment_service,
        "assign",
        lambda session_id: {"experiment_id": "exp", "variant_id": "control", "strategy": "ranked"},
    )
    monkeypatch.setattr(
        ai_push_service,
        "decide",
        lambda context, **kwargs: {
            "items": [{"id": "MCD-REGULAR", "score": 1, "reasons": []}],
            "strategy": "ranked",
            "decision_id": "decision-test",
        },
    )

    result = asyncio.run(
        ai_push_service.generate_three(
            "session-assist-test",
            cart_ids=[],
            scope=object(),
        )
    )

    assert captured["surface"] == "assist_recommend"
    assert captured["exclude_ids"] == []
    assert [item["id"] for item in result] == ["MCD-REGULAR"]
    assert result[0]["push_text"] == "適合現在享用的餐點。"
