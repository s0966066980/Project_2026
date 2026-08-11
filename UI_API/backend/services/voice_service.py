"""Optional single-pass emotion observation for a completed Voice Turn.

The customer-facing voice pipeline lives in `modules.voice_turn`; this module only
schedules the optional emotion observation derived from a finished Voice Turn.
"""
import asyncio
import os
import shutil
import tempfile
import threading

from services import emotion_service

_background_emotion_tasks: set[asyncio.Task] = set()

async def _analyze_current_voice_emotion_pair(
    *,
    session_id: str,
    media_path: str,
    speech_text: str,
    emotion_round_id: str,
    voice_turn_id: str,
    voice_turn_index: int,
) -> dict | None:
    """Analyze one completed turn for media-free observability."""
    if emotion_service.capture_mode() != "voice_only":
        return None

    try:
        result = await emotion_service.analyze_event(
            session_id=session_id,
            media_path=media_path,
            event_type="voice_mode_ended",
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
    if emotion_service.capture_mode() != "voice_only":
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
