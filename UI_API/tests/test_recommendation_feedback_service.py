import importlib
from datetime import datetime, timedelta


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

    from services import recommendation_feedback_service
    importlib.reload(recommendation_feedback_service)

    def fake_config_get(key, default=None):
        values = {
            "RECOMMENDATION_IGNORE_FEEDBACK_ENABLED": True,
            "RECOMMENDATION_IGNORE_WINDOW_MINUTES": 60,
            "RECOMMENDATION_FEEDBACK_EVENT_LIMIT": 100,
            "RECOMMENDATION_IGNORED_ITEM_PENALTY": 2,
            "RECOMMENDATION_IGNORED_OFFER_PENALTY": 1,
            "RECOMMENDATION_IGNORED_ITEM_EXCLUDE_THRESHOLD": 2,
        }
        return values.get(key, default)

    monkeypatch.setattr(recommendation_feedback_service.config, "get", fake_config_get)
    return recommendation_feedback_service, recommendation_event_repository


def _event(session_id, event_type, item_id, *, offer_ids=None, minutes_ago=5, member_phone_masked=""):
    return {
        "event_id": f"{session_id}-{event_type}-{item_id}-{minutes_ago}",
        "recommendation_id": f"rec-{item_id}",
        "session_id": session_id,
        "event_type": event_type,
        "item_id": item_id,
        "metadata": {"offer_ids": offer_ids or []},
        "member_phone_masked": member_phone_masked,
        "timestamp": (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(),
    }


def test_build_feedback_context_counts_recent_ignored_item_and_offer(tmp_path, monkeypatch):
    service, repository = _service(tmp_path, monkeypatch)
    repository.append_recommendation_events([
        _event("s1", "recommendation_ignored", "MCD012", offer_ids=["fries_offer"], minutes_ago=10),
        _event("s2", "recommendation_ignored", "MCD001", offer_ids=["other_offer"], minutes_ago=10),
    ])

    feedback = service.build_feedback_context("s1")

    assert feedback["ignored_item_ids"] == ["MCD012"]
    assert feedback["ignored_offer_ids"] == ["fries_offer"]
    assert feedback["penalty_by_item_id"] == {"MCD012": 2}
    assert feedback["penalty_by_offer_id"] == {"fries_offer": 1}


def test_later_positive_event_clears_ignored_feedback(tmp_path, monkeypatch):
    service, repository = _service(tmp_path, monkeypatch)
    repository.append_recommendation_events([
        _event("s1", "recommendation_ignored", "MCD012", offer_ids=["fries_offer"], minutes_ago=10),
        _event("s1", "recommendation_added_to_cart", "MCD012", offer_ids=["fries_offer"], minutes_ago=5),
    ])

    feedback = service.build_feedback_context("s1")

    assert feedback["ignored_item_ids"] == []
    assert feedback["ignored_offer_ids"] == []
    assert feedback["penalty_by_item_id"] == {}
    assert feedback["penalty_by_offer_id"] == {}


def test_positive_before_ignored_does_not_suppress_later_feedback(tmp_path, monkeypatch):
    service, repository = _service(tmp_path, monkeypatch)
    repository.append_recommendation_events([
        _event("s1", "recommendation_clicked", "MCD012", offer_ids=["fries_offer"], minutes_ago=10),
        _event("s1", "recommendation_ignored", "MCD012", offer_ids=["fries_offer"], minutes_ago=5),
    ])

    feedback = service.build_feedback_context("s1")

    assert feedback["penalty_by_item_id"] == {"MCD012": 2}
    assert feedback["penalty_by_offer_id"] == {"fries_offer": 1}


def test_member_masked_events_are_included_and_threshold_excludes(tmp_path, monkeypatch):
    service, repository = _service(tmp_path, monkeypatch)
    repository.append_recommendation_events([
        _event("old-session", "recommendation_ignored", "MCD012", minutes_ago=20, member_phone_masked="0912-***-678"),
        _event("new-session", "recommendation_ignored", "MCD012", minutes_ago=10, member_phone_masked="0912-***-678"),
    ])

    feedback = service.build_feedback_context("current-session", member_phone_masked="0912-***-678")

    assert feedback["penalty_by_item_id"] == {"MCD012": 4}
    assert feedback["exclude_item_ids"] == ["MCD012"]
