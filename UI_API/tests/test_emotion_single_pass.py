import asyncio

from models.multimodal_evidence import MultimodalEvidence
from services import emotion_service


def _evidence(*, status="ok", quality="ok", has_evidence=True):
    return MultimodalEvidence(
        provider="r1_omni",
        model_version="test",
        timestamp="2026-08-11T00:00:00+00:00",
        confidence=0.9 if has_evidence else None,
        signals={
            "emotion": "happy",
            "intensity": "high",
            "facial": "smiling",
            "vocal": "bright tone",
            "description": "顧客整體表現開心。",
        } if has_evidence else {},
        quality=quality,
        latency_ms=1,
        status=status,
        has_evidence=has_evidence,
    )


def _capture_records(monkeypatch):
    records = []

    def append(row):
        records.append(dict(row))
        return row

    monkeypatch.setattr(emotion_service.emotion_log_repository, "append_record", append)
    return records


def test_success_persists_only_the_seven_record_columns(monkeypatch):
    records = _capture_records(monkeypatch)
    monkeypatch.setattr(emotion_service, "model_profiles", lambda: [{"ready": True}])
    monkeypatch.setattr(emotion_service, "collect_evidence", lambda *_args, **_kwargs: _evidence())

    result = asyncio.run(emotion_service.analyze_live_diagnostic("/tmp/test.webm"))

    assert result["status"] == "ok"
    assert result["emotion"] == "happy"
    assert set(records[0]) == {
        "timestamp", "event", "model", "emotion_intensity", "expression", "voice", "description"
    }
    assert "emotion" not in records[0]


def test_unready_model_is_skipped_before_submission_without_a_record(monkeypatch):
    records = _capture_records(monkeypatch)
    monkeypatch.setattr(
        emotion_service,
        "model_profiles",
        lambda: [{"ready": False, "status": "unavailable", "message": "down"}],
    )

    result = asyncio.run(emotion_service.analyze_live_diagnostic("/tmp/test.webm"))

    assert result["status"] == "skipped"
    assert result["reason"] == "model_not_ready"
    assert result["provider"]["status"] == "unavailable"
    assert records == []


def test_failure_after_inference_submission_creates_safe_media_free_record(monkeypatch):
    records = _capture_records(monkeypatch)
    monkeypatch.setattr(emotion_service, "model_profiles", lambda: [{"ready": True}])
    monkeypatch.setattr(emotion_service, "collect_evidence", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))

    result = asyncio.run(emotion_service.analyze_live_diagnostic("/tmp/test.webm"))

    assert result["status"] == "error"
    assert result["emotion"] == "undetermined"
    assert len(records) == 1
    assert records[0]["emotion_intensity"] == "undetermined"
    assert all(token not in records[0] for token in ("media", "prompt", "transcript", "session_id"))


def test_incomplete_capture_is_skipped_without_a_record(monkeypatch):
    records = _capture_records(monkeypatch)
    monkeypatch.setattr(emotion_service, "model_profiles", lambda: [{"ready": True}])
    monkeypatch.setattr(
        emotion_service,
        "collect_evidence",
        lambda *_args, **_kwargs: _evidence(status="skipped", quality="skipped", has_evidence=False),
    )

    result = asyncio.run(emotion_service.analyze_live_diagnostic("/tmp/test.webm"))

    assert result == {"status": "skipped", "reason": "incomplete_capture"}
    assert records == []
