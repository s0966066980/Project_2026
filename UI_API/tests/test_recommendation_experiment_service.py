import importlib


def test_assignment_is_stable_for_same_session(monkeypatch):
    from services import recommendation_experiment_service
    importlib.reload(recommendation_experiment_service)

    def fake_config_get(key, default=None):
        values = {
            "RECOMMENDATION_EXPERIMENT_ENABLED": True,
            "RECOMMENDATION_EXPERIMENT_ID": "recommendation_strategy_v1",
            "RECOMMENDATION_EXPERIMENT_VARIANTS": [
                {"variant_id": "control", "strategy": "weighted_random", "traffic": 50},
                {"variant_id": "ranked", "strategy": "ranked_top_score", "traffic": 50},
            ],
        }
        return values.get(key, default)

    monkeypatch.setattr(recommendation_experiment_service.config, "get", fake_config_get)

    first = recommendation_experiment_service.assign("session-a")
    second = recommendation_experiment_service.assign("session-a")

    assert first == second
    assert first["experiment_id"] == "recommendation_strategy_v1"
    assert first["variant_id"] in {"control", "ranked"}
    assert first["strategy"] in {"weighted_random", "ranked_top_score"}


def test_assignment_falls_back_to_first_variant_when_disabled(monkeypatch):
    from services import recommendation_experiment_service
    importlib.reload(recommendation_experiment_service)

    def fake_config_get(key, default=None):
        values = {
            "RECOMMENDATION_EXPERIMENT_ENABLED": False,
            "RECOMMENDATION_EXPERIMENT_ID": "recommendation_strategy_v1",
            "RECOMMENDATION_EXPERIMENT_VARIANTS": [
                {"variant_id": "control", "strategy": "weighted_random", "traffic": 50},
                {"variant_id": "ranked", "strategy": "ranked_top_score", "traffic": 50},
            ],
        }
        return values.get(key, default)

    monkeypatch.setattr(recommendation_experiment_service.config, "get", fake_config_get)

    assignment = recommendation_experiment_service.assign("session-a")

    assert assignment == {
        "enabled": False,
        "experiment_id": "recommendation_strategy_v1",
        "variant_id": "control",
        "strategy": "weighted_random",
    }
