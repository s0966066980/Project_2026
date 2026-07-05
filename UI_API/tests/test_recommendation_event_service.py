import importlib


def _service(tmp_path, monkeypatch):
    from repositories import recommendation_event_repository
    importlib.reload(recommendation_event_repository)
    monkeypatch.setattr(
        recommendation_event_repository,
        "RECOMMENDATION_EVENTS_PATH",
        str(tmp_path / "recommendation_events.json"),
    )
    recommendation_event_repository._cache.clear()
    monkeypatch.setattr(recommendation_event_repository.postgres_utils, "use_postgres", lambda: False)

    from services import recommendation_event_service
    importlib.reload(recommendation_event_service)
    monkeypatch.setattr(recommendation_event_service.member_service, "get_session_member", lambda session_id: None)
    return recommendation_event_service, recommendation_event_repository


def test_record_recommendation_event_normalizes_payload(tmp_path, monkeypatch):
    service, repository = _service(tmp_path, monkeypatch)

    event = service.record_recommendation_event({
        "session_id": "s-normalize",
        "event_type": "recommendation_shown",
        "surface": "ai_push",
        "source": "recommendation_engine",
        "item_id": "MCD001",
        "item_name": "大麥克套餐",
        "score": 5,
        "reasons": ["member_usual", "global_popular"],
        "offer_ids": ["offer_big_mac"],
        "experiment_id": "recommendation_strategy_v1",
        "variant_id": "control",
        "strategy": "weighted_random",
        "metadata": {"push_text": "推薦文案", "unsafe": "drop"},
    })

    assert event["event_type"] == "recommendation_shown"
    assert event["recommendation_id"].startswith("rec_s-normalize_ai_push_MCD001")
    assert event["is_member"] is False
    assert event["metadata"] == {
        "push_text": "推薦文案",
        "strategy": "weighted_random",
        "offer_id": "offer_big_mac",
        "offer_ids": ["offer_big_mac"],
        "experiment_id": "recommendation_strategy_v1",
        "variant_id": "control",
    }
    assert repository.get_recommendation_events("s-normalize", 10)[0]["item_id"] == "MCD001"


def test_checkout_records_checked_out_and_ignored_events(tmp_path, monkeypatch):
    service, repository = _service(tmp_path, monkeypatch)
    service.record_recommendation_event({
        "session_id": "s1",
        "event_type": "recommendation_shown",
        "recommendation_id": "rec-1",
        "surface": "ai_push",
        "source": "recommendation_engine",
        "item_id": "MCD001",
        "score": 4,
        "reasons": ["member_usual"],
        "metadata": {
            "offer_ids": ["offer_big_mac"],
            "experiment_id": "recommendation_strategy_v1",
            "variant_id": "control",
            "strategy": "weighted_random",
        },
    })
    service.record_recommendation_event({
        "session_id": "s1",
        "event_type": "recommendation_shown",
        "recommendation_id": "rec-2",
        "surface": "assist_recommend",
        "source": "recommendation_engine",
        "item_id": "MCD012",
        "metadata": {"offer_id": "offer_fries"},
    })

    appended = service.record_checkout_recommendation_events(
        "s1",
        ["MCD001"],
        [{"id": "MCD001", "quantity": 2}],
        [{"id": "MCD001", "source": "ai_push"}],
        ["MCD001", "MCD012"],
    )
    by_type = {event["event_type"]: event for event in appended}

    assert by_type["recommendation_checked_out"]["item_id"] == "MCD001"
    assert by_type["recommendation_checked_out"]["quantity"] == 2
    assert by_type["recommendation_checked_out"]["recommendation_id"] == "rec-1"
    assert by_type["recommendation_checked_out"]["metadata"]["offer_ids"] == ["offer_big_mac"]
    assert by_type["recommendation_checked_out"]["metadata"]["variant_id"] == "control"
    assert by_type["recommendation_ignored"]["item_id"] == "MCD012"
    assert by_type["recommendation_ignored"]["metadata"]["offer_ids"] == ["offer_fries"]

    stats = service.build_recommendation_event_stats(repository.get_recommendation_events("s1", 20))
    assert stats["event_type_counts"]["recommendation_shown"] == 2
    assert stats["event_type_counts"]["recommendation_checked_out"] == 1
    assert stats["offer_counts"]["offer_big_mac"]["recommendation_checked_out"] == 1
    assert stats["offer_counts"]["offer_fries"]["recommendation_ignored"] == 1
    assert stats["variant_counts"]["recommendation_strategy_v1:control"]["recommendation_checked_out"] == 1
    assert stats["checkout_rate"] == 0.5
