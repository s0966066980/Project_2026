from uuid import UUID


def test_recommendation_decision_has_durable_metadata_and_rank():
    from models.commercial_scope import CommercialScope
    from modules.recommendation.application import decide
    from services.analytics_pipeline_service import InMemoryAnalyticsSink

    context = {
        "audience": "guest",
        "preferences": {"usual_item_ids": [], "recent_item_ids": [], "preferred_categories": [], "frequent_pairs": []},
        "global": {"popular_item_ids": ["MCD001"], "priority_categories": []},
        "controls": {"exclude_item_ids": [], "surface": "ai_push"},
        "cart": {"item_ids": []},
        "rag": {"offers": []},
        "availability": {"low_stock_item_ids": [], "low_stock_penalty": 0},
        "menu_items": [{"id": "MCD001", "name": "大麥克", "price": 80, "category": "主餐"}],
    }
    scope = CommercialScope(
        UUID("00000000-0000-4000-8000-000000000010"),
        UUID("00000000-0000-4000-8000-000000000020"),
        UUID("00000000-0000-4000-8000-000000000030"),
    )
    sink = InMemoryAnalyticsSink()

    result = decide(
        context,
        session_id="session-1",
        scope=scope,
        limit=1,
        randomize=False,
        experiment={
            "experiment_id": "strategy-v1",
            "variant_id": "control",
            "strategy": "ranked_top_score",
        },
        decision_id="decision-fixed",
        sink=sink,
    )

    assert result["decision_id"] == "decision-fixed"
    assert result["strategy_version"] == "recommendation-v1"
    assert result["variant_id"] == "control"
    assert result["fallback_status"] == "not_used"
    assert result["items"][0]["rank"] == 1
    assert result["items"][0]["decision_id"] == "decision-fixed"
    assert sink.events[0]["type"] == "commercial_touch.decision"
