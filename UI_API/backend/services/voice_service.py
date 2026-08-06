"""Voice emotion observation: pair a Voice Turn's media with its speech text.

The customer-facing voice pipeline lives in `modules.voice_turn`; this module only
schedules the optional emotion observation derived from a finished Voice Turn.
"""
import asyncio
import os
import shutil
import subprocess
import tempfile
import threading
import time

import config
from services import emotion_service

_background_emotion_tasks: set[asyncio.Task] = set()


def _media_has_video_track(media_path: str) -> bool:
    """Return whether a media file contains a decodable video stream."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not media_path or not os.path.exists(media_path):
        return False
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=index",
                "-of", "csv=p=0",
                media_path,
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return completed.returncode == 0 and bool(completed.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False




async def _analyze_current_voice_emotion_pair(
    *,
    session_id: str,
    media_path: str,
    speech_text: str,
    emotion_round_id: str,
    voice_turn_id: str,
    voice_turn_index: int,
) -> dict | None:
    """Analyze one completed turn for later-turn assistance and observability."""
    if (
        not emotion_service.is_enabled()
        or config.get("EMOTION_EVENT_VOICE", True) is False
    ):
        return None

    pair_id = f"{emotion_round_id}:{voice_turn_id or voice_turn_index}"[:160]
    common = {
        "session_id": session_id,
        "media_path": media_path,
        "event_type": "voice_mode_ended",
        "update_voice_session": True,
        "emotion_round_id": emotion_round_id,
        "voice_turn_id": voice_turn_id,
        "voice_turn_index": voice_turn_index,
        "observed_at_ms": int(time.time() * 1000),
        "comparison_pair_id": pair_id,
        "cache_voice_observation": True,
    }
    try:
        mode = str(config.get("EMOTION_ANALYSIS_MODE", "media_plus_stt") or "")
        if mode not in {"media_only", "media_plus_stt", "paired"}:
            mode = "media_plus_stt"
        if not speech_text or config.get("EMOTION_INCLUDE_STT", True) is False:
            mode = "media_only"

        if mode == "media_only":
            result = await emotion_service.analyze_event(
                speech_text="",
                analysis_variant="media_only",
                **common,
            )
        elif mode == "media_plus_stt":
            result = await emotion_service.analyze_event(
                speech_text=speech_text,
                analysis_variant="media_plus_stt",
                **common,
            )
        else:
            result, _baseline = await asyncio.gather(
                emotion_service.analyze_event(
                    speech_text=speech_text,
                    analysis_variant="media_plus_stt",
                    **common,
                ),
                emotion_service.analyze_event(
                    speech_text="",
                    analysis_variant="media_only",
                    **common,
                ),
            )
    except Exception as exc:
        print(f"⚠️ 本次語音情緒分析失敗，將不影響語音回覆: {exc}")
        return None
    return result if result.get("status") == "ok" and result.get("emotion") else None


def _schedule_voice_emotion_observation(
    *,
    session_id: str,
    media_path: str,
    speech_text: str,
    emotion_round_id: str,
    voice_turn_id: str,
    voice_turn_index: int,
) -> asyncio.Task | None:
    """Run slow emotion inference outside the current Voice Turn critical path.

    Durable Voice Turns execute their effects in a worker thread, while the
    legacy async path calls this function from an event loop. Support both
    callers without constructing an orphaned coroutine when no loop is running.
    """
    if (
        not emotion_service.is_enabled()
        or config.get("EMOTION_EVENT_VOICE", True) is False
    ):
        return None

    suffix = os.path.splitext(media_path)[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        background_path = tmp.name
    try:
        shutil.copyfile(media_path, background_path)
    except Exception:
        try:
            os.remove(background_path)
        except OSError:
            pass
        raise

    async def _run() -> None:
        try:
            if not await asyncio.to_thread(_media_has_video_track, background_path):
                return
            await _analyze_current_voice_emotion_pair(
                session_id=session_id,
                media_path=background_path,
                speech_text=speech_text,
                emotion_round_id=emotion_round_id,
                voice_turn_id=voice_turn_id,
                voice_turn_index=voice_turn_index,
            )
        except Exception as exc:
            print(f"⚠️ 背景語音情緒分析失敗: {exc}")
        finally:
            try:
                os.remove(background_path)
            except OSError:
                pass

    task_name = f"voice-emotion-{voice_turn_id or voice_turn_index}"
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        def _thread_runner() -> None:
            asyncio.run(_run())

        thread = threading.Thread(target=_thread_runner, name=task_name, daemon=True)
        try:
            thread.start()
        except Exception:
            try:
                os.remove(background_path)
            except OSError:
                pass
            raise
        return None

    task = loop.create_task(_run(), name=task_name)
    _background_emotion_tasks.add(task)
    task.add_done_callback(_background_emotion_tasks.discard)
    return task

