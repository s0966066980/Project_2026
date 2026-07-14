import importlib


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐"},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
    {"id": "MCD030", "name": "可口可樂(中)", "price": 35, "category": "飲料"},
]


def _context():
    return {
        "audience": "member",
        "preferences": {
            "usual_item_ids": ["MCD012"],
            "recent_item_ids": ["MCD030"],
            "preferred_categories": [],
            "frequent_pairs": [],
        },
        "global": {
            "popular_item_ids": ["MCD001"],
            "priority_categories": ["飲料"],
        },
        "controls": {
            "exclude_item_ids": [],
            "surface": "voice",
        },
        "cart": {
            "item_ids": [],
        },
        "rag": {
            "offers": [],
        },
        "availability": {
            "low_stock_item_ids": [],
            "low_stock_penalty": 0,
        },
        "menu_items": list(MENU),
    }


def test_build_candidates_scores_member_popular_and_priority(monkeypatch):
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    def fake_config_get(key, default=None):
        values = {
            "MEMBER_PUSH_WEIGHT": 8,
            "RECOMMENDATION_POPULAR_WEIGHT": 3,
            "RECOMMENDATION_RECENT_WEIGHT": 4,
            "RECOMMENDATION_PRIORITY_CATEGORY_WEIGHT": 5,
        }
        return values.get(key, default)

    monkeypatch.setattr(recommendation_engine_service.config, "get", fake_config_get)
    candidates = recommendation_engine_service.build_candidates(_context())
    by_id = {candidate["id"]: candidate for candidate in candidates}

    assert by_id["MCD012"]["score"] == 8
    assert "member_usual" in by_id["MCD012"]["reasons"]
    assert by_id["MCD001"]["score"] == 3
    assert "global_popular" in by_id["MCD001"]["reasons"]
    assert by_id["MCD030"]["score"] == 5
    assert "member_recent" in by_id["MCD030"]["reasons"]
    assert "priority_category" in by_id["MCD030"]["reasons"]


def test_recommend_excludes_ids_and_returns_unique_items():
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    context = _context()
    context["controls"]["exclude_item_ids"] = ["MCD001"]
    result = recommendation_engine_service.recommend(context, limit=3, randomize=False)
    ids = [item["id"] for item in result["items"]]

    assert "MCD001" not in ids
    assert len(ids) == len(set(ids))
    assert ids == ["MCD012", "MCD030"]


def test_recommend_ranked_strategy_returns_top_scores():
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    experiment = {
        "experiment_id": "recommendation_strategy_v1",
        "variant_id": "ranked",
        "strategy": "ranked_top_score",
    }
    result = recommendation_engine_service.recommend(
        _context(),
        limit=2,
        randomize=True,
        strategy="ranked_top_score",
        experiment=experiment,
    )
    ids = [item["id"] for item in result["items"]]

    assert ids == ["MCD012", "MCD001"]
    assert result["strategy"] == "ranked_top_score"
    assert result["experiment_id"] == "recommendation_strategy_v1"
    assert result["variant_id"] == "ranked"


def test_build_candidates_scores_member_category_and_pairing(monkeypatch):
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    def fake_config_get(key, default=None):
        values = {
            "RECOMMENDATION_CATEGORY_WEIGHT": 6,
            "RECOMMENDATION_PAIR_WEIGHT": 9,
        }
        return values.get(key, default)

    monkeypatch.setattr(recommendation_engine_service.config, "get", fake_config_get)
    context = _context()
    context["preferences"]["preferred_categories"] = ["飲料"]
    context["preferences"]["frequent_pairs"] = [{
        "item_ids": ["MCD001", "MCD012"],
        "count": 3,
    }]
    context["cart"]["item_ids"] = ["MCD001"]

    candidates = recommendation_engine_service.build_candidates(context)
    by_id = {candidate["id"]: candidate for candidate in candidates}

    assert by_id["MCD012"]["score"] == 9
    assert "member_pairing" in by_id["MCD012"]["reasons"]
    assert by_id["MCD030"]["score"] == 6
    assert "member_category" in by_id["MCD030"]["reasons"]


def test_format_voice_recommendation_context():
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    result = recommendation_engine_service.recommend(_context(), limit=2, randomize=False)
    section = recommendation_engine_service.format_voice_recommendation_context(result)

    assert "推薦候選 TOP 3" in section
    assert "MCD012" in section
    assert "顧客未明確確認時不要直接加入購物車" in section


def test_rag_member_offer_scores_only_for_member(monkeypatch):
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    def fake_config_get(key, default=None):
        values = {
            "RECOMMENDATION_RAG_OFFER_WEIGHT": 7,
            "RECOMMENDATION_RAG_CATEGORY_WEIGHT": 2,
        }
        return values.get(key, default)

    monkeypatch.setattr(recommendation_engine_service.config, "get", fake_config_get)
    context = _context()
    context["preferences"]["usual_item_ids"] = []
    context["preferences"]["recent_item_ids"] = []
    context["global"]["popular_item_ids"] = []
    context["global"]["priority_categories"] = []
    context["rag"]["offers"] = [{
        "offer_id": "member_fries",
        "title": "會員薯條活動",
        "member_only": True,
        "item_ids": ["MCD012"],
        "score_boost": 7,
    }]

    by_id = {candidate["id"]: candidate for candidate in recommendation_engine_service.build_candidates(context)}
    assert by_id["MCD012"]["score"] == 7
    assert by_id["MCD012"]["offer_ids"] == ["member_fries"]
    assert "member_offer" in by_id["MCD012"]["reasons"]
    assert "rag_offer" in by_id["MCD012"]["reasons"]

    context["audience"] = "guest"
    by_id = {candidate["id"]: candidate for candidate in recommendation_engine_service.build_candidates(context)}
    assert by_id["MCD012"]["score"] == 1
    assert "rag_offer" not in by_id["MCD012"]["reasons"]


def test_rag_category_offer_requires_cart_when_configured():
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    context = _context()
    context["preferences"]["usual_item_ids"] = []
    context["preferences"]["recent_item_ids"] = []
    context["global"]["popular_item_ids"] = []
    context["global"]["priority_categories"] = []
    context["rag"]["offers"] = [{
        "offer_id": "combo_drink",
        "title": "主餐搭飲料",
        "member_only": False,
        "categories": ["飲料"],
        "required_cart_item_ids": ["MCD001"],
        "category_score_boost": 6,
    }]

    by_id = {candidate["id"]: candidate for candidate in recommendation_engine_service.build_candidates(context)}
    assert by_id["MCD030"]["score"] == 1

    context["cart"]["item_ids"] = ["MCD001"]
    by_id = {candidate["id"]: candidate for candidate in recommendation_engine_service.build_candidates(context)}
    assert by_id["MCD030"]["score"] == 6
    assert "rag_category_offer" in by_id["MCD030"]["reasons"]


def test_rag_offer_requires_every_configured_cart_item():
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    context = _context()
    context["preferences"]["usual_item_ids"] = []
    context["preferences"]["recent_item_ids"] = []
    context["global"]["popular_item_ids"] = []
    context["global"]["priority_categories"] = []
    context["rag"]["offers"] = [{
        "offer_id": "complete_combo_drink",
        "title": "完整套餐加購飲料",
        "categories": ["飲料"],
        "required_cart_item_ids": ["MCD001", "MCD012"],
        "category_score_boost": 6,
    }]

    context["cart"]["item_ids"] = ["MCD001"]
    by_id = {candidate["id"]: candidate for candidate in recommendation_engine_service.build_candidates(context)}
    assert by_id["MCD030"]["score"] == 1
    assert "rag_category_offer" not in by_id["MCD030"]["reasons"]

    context["cart"]["item_ids"] = ["MCD001", "MCD012"]
    by_id = {candidate["id"]: candidate for candidate in recommendation_engine_service.build_candidates(context)}
    assert by_id["MCD030"]["score"] == 6
    assert "rag_category_offer" in by_id["MCD030"]["reasons"]


def test_recent_ignored_feedback_penalizes_item_and_offer():
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    context = _context()
    context["preferences"]["usual_item_ids"] = []
    context["preferences"]["recent_item_ids"] = []
    context["global"]["popular_item_ids"] = []
    context["global"]["priority_categories"] = []
    context["rag"]["offers"] = [{
        "offer_id": "fries_offer",
        "title": "薯條活動",
        "item_ids": ["MCD012"],
        "score_boost": 5,
    }]
    context["feedback"] = {
        "ignored_item_ids": ["MCD012"],
        "ignored_offer_ids": ["fries_offer"],
        "penalty_by_item_id": {"MCD012": 2},
        "penalty_by_offer_id": {"fries_offer": 1},
        "exclude_item_ids": [],
    }

    by_id = {candidate["id"]: candidate for candidate in recommendation_engine_service.build_candidates(context)}

    assert by_id["MCD012"]["score"] == 2
    assert by_id["MCD012"]["feedback_penalty"] == 3
    assert "recently_ignored" in by_id["MCD012"]["reasons"]


def test_low_stock_availability_penalizes_candidate(monkeypatch):
    from services import recommendation_engine_service
    importlib.reload(recommendation_engine_service)

    def fake_config_get(key, default=None):
        values = {
            "MEMBER_PUSH_WEIGHT": 5,
            "RECOMMENDATION_LOW_STOCK_PENALTY": 2,
        }
        return values.get(key, default)

    monkeypatch.setattr(recommendation_engine_service.config, "get", fake_config_get)
    context = _context()
    context["global"]["popular_item_ids"] = []
    context["global"]["priority_categories"] = []
    context["availability"] = {
        "low_stock_item_ids": ["MCD012"],
        "low_stock_penalty": 2,
    }

    by_id = {candidate["id"]: candidate for candidate in recommendation_engine_service.build_candidates(context)}

    assert by_id["MCD012"]["score"] == 3
    assert by_id["MCD012"]["availability_penalty"] == 2
    assert "low_stock" in by_id["MCD012"]["reasons"]
