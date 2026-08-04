import asyncio
import threading
import time
from types import SimpleNamespace


def test_voice_order_draft_is_unselected_and_bounded():
    from services.voice_service import _build_voice_order_draft

    menu = [
        {"id": "MCD001", "name": "大麥克"},
        {"id": "MCD002", "name": "薯條"},
        {"id": "MCD003", "name": "可樂"},
        {"id": "MCD004", "name": "蘋果派"},
        {"id": "MCD005", "name": "咖啡"},
    ]
    draft = _build_voice_order_draft(
        "我要兩份大麥克",
        [{"action": "add", "id": "MCD001", "quantity": 2}],
        menu,
    )

    assert draft["items"] == [{"id": "MCD001", "quantity": 2, "selected": False}]
    assert draft["recommendation_ids"] == ["MCD002", "MCD003", "MCD004"]
    assert draft["clarification_ids"] == []


def test_uncertain_voice_order_requires_explicit_choice():
    from services.voice_service import _build_voice_order_draft

    menu = [
        {"id": "MCD001", "name": "大麥克"},
        {"id": "MCD002", "name": "雙層牛肉吉事堡"},
        {"id": "MCD003", "name": "麥香魚"},
        {"id": "MCD004", "name": "薯條"},
    ]
    draft = _build_voice_order_draft("我要一個漢堡", [], menu)

    assert draft["items"] == []
    assert draft["recommendation_ids"] == []
    assert draft["clarification_ids"] == ["MCD001", "MCD002", "MCD003"]


def test_non_order_question_does_not_open_order_draft():
    from services.voice_service import _build_voice_order_draft

    draft = _build_voice_order_draft(
        "大麥克多少錢",
        [{"action": "add", "id": "MCD001", "quantity": 1}],
        [{"id": "MCD001", "name": "大麥克"}],
    )

    assert draft == {"items": [], "recommendation_ids": [], "clarification_ids": []}


def test_progressive_voice_text_never_claims_cart_was_changed():
    from services.voice_service import _safe_progressive_voice_text

    assert _safe_progressive_voice_text("好的，已為您加入大麥克一份。") == (
        "已整理您提到的餐點，請在畫面上勾選並確認。"
    )
    assert _safe_progressive_voice_text("好的，為您加入一份大麥克。") == (
        "已整理您提到的餐點，請在畫面上勾選並確認。"
    )
    assert _safe_progressive_voice_text("I added a Big Mac.") == "已整理您提到的餐點，請在畫面上勾選並確認。"
    assert _safe_progressive_voice_text("大麥克單價是 79 元。") == "大麥克單價是 79 元。"


def test_emotion_observation_is_scheduled_without_blocking(tmp_path, monkeypatch):
    from services import voice_service

    media = tmp_path / "voice.webm"
    media.write_bytes(b"voice")
    started = asyncio.Event()
    release = asyncio.Event()

    monkeypatch.setattr(voice_service.emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(voice_service.config, "get", lambda key, default=None: default)
    monkeypatch.setattr(voice_service, "_media_has_video_track", lambda _path: True)

    async def slow_analysis(**_kwargs):
        started.set()
        await release.wait()

    monkeypatch.setattr(voice_service, "_analyze_current_voice_emotion_pair", slow_analysis)

    async def scenario():
        task = voice_service._schedule_voice_emotion_observation(
            session_id="s1",
            media_path=str(media),
            speech_text="大麥克",
            emotion_round_id="r1",
            voice_turn_id="v1",
            voice_turn_index=1,
        )
        assert task is not None
        await asyncio.wait_for(started.wait(), timeout=0.2)
        assert not task.done()
        release.set()
        await asyncio.wait_for(task, timeout=0.2)

    asyncio.run(scenario())


def test_audio_only_voice_turn_skips_multimodal_model(tmp_path, monkeypatch):
    from services import voice_service

    media = tmp_path / "voice.webm"
    media.write_bytes(b"audio-only")
    analyzed = False

    monkeypatch.setattr(voice_service.emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(voice_service.config, "get", lambda key, default=None: default)
    monkeypatch.setattr(voice_service, "_media_has_video_track", lambda _path: False)

    async def should_not_run(**_kwargs):
        nonlocal analyzed
        analyzed = True

    monkeypatch.setattr(voice_service, "_analyze_current_voice_emotion_pair", should_not_run)

    async def scenario():
        task = voice_service._schedule_voice_emotion_observation(
            session_id="audio-session",
            media_path=str(media),
            speech_text="大麥克",
            emotion_round_id="audio-round",
            voice_turn_id="audio-turn",
            voice_turn_index=1,
        )
        assert task is not None
        await task

    asyncio.run(scenario())
    assert analyzed is False


def test_emotion_observation_can_schedule_from_voice_worker_thread(tmp_path, monkeypatch):
    from services import voice_service

    media = tmp_path / "worker-voice.webm"
    media.write_bytes(b"voice")
    completed = threading.Event()
    background_paths = []

    monkeypatch.setattr(voice_service.emotion_service, "is_enabled", lambda: True)
    monkeypatch.setattr(voice_service.config, "get", lambda key, default=None: default)
    monkeypatch.setattr(voice_service, "_media_has_video_track", lambda _path: True)

    async def analysis(**kwargs):
        background_paths.append(kwargs["media_path"])
        completed.set()

    monkeypatch.setattr(voice_service, "_analyze_current_voice_emotion_pair", analysis)

    task = voice_service._schedule_voice_emotion_observation(
        session_id="worker-session",
        media_path=str(media),
        speech_text="大麥克",
        emotion_round_id="worker-round",
        voice_turn_id="worker-turn",
        voice_turn_index=1,
    )

    assert task is None
    assert completed.wait(timeout=0.5)
    assert len(background_paths) == 1
    for _attempt in range(50):
        if not voice_service.os.path.exists(background_paths[0]):
            break
        time.sleep(0.01)
    assert not voice_service.os.path.exists(background_paths[0])


def test_durable_voice_assistant_bounds_generation_and_mentioned_items(monkeypatch):
    from modules.voice_turn import runtime

    captured = []

    def generate(request):
        captured.append(request)
        return SimpleNamespace(
            parsed={
                "ai_response": "會員可享九折優惠。",
                "cart_actions": [],
                "mentioned_ids": [f"MCD{index:03d}" for index in range(1, 139)],
            }
        )

    monkeypatch.setattr(runtime.llm_gateway_service, "generate", generate)
    assistant = runtime.ProductionAssistant()
    result = assistant.assist(
        transcript="請問會員有什麼優惠？",
        candidates=[
            {"item_id": f"MCD{index:03d}", "name": f"品項{index}", "price": index, "available": True}
            for index in range(1, 139)
        ],
        operation_key="turn-1:assistant",
    )

    assert captured[0].max_tokens == 96
    assert result["mentioned_ids"] == []
