"""Repository for emotion video clip storage and index management."""

import json
import os
import re
import secrets
import shutil
import time

import config


def safe_session_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value or "session"))[:80] or "session"


def safe_clip_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or ""))[:120]


def emotion_clip_dir(session_id: str) -> str:
    safe_id = safe_session_id(session_id)
    return os.path.join(config.EMOTION_ORDER_MEDIA_DIR, safe_id)


def _emotion_clip_index_path(session_id: str) -> str:
    return os.path.join(emotion_clip_dir(session_id), "index.json")


def load_clip_index(session_id: str) -> list:
    index_path = _emotion_clip_index_path(session_id)
    if not os.path.exists(index_path):
        return []
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_clip_index(session_id: str, clips: list):
    os.makedirs(emotion_clip_dir(session_id), exist_ok=True)
    with open(_emotion_clip_index_path(session_id), "w", encoding="utf-8") as f:
        json.dump(clips, f, ensure_ascii=False, indent=2)


def _clip_created_ts(clip: dict) -> float:
    try:
        return time.mktime(time.strptime(str(clip.get("created_at", "")), "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 0.0


def _cleanup_expired_raw_clips(session_id: str, clips: list) -> list:
    retention_min = float(config.get("PRIVACY_RAW_CLIP_RETENTION_MINUTES", 10) or 10)
    if retention_min <= 0:
        return clips
    now = time.time()
    clip_dir = emotion_clip_dir(session_id)
    for clip in clips:
        if not isinstance(clip, dict) or not clip.get("raw_clip_saved"):
            continue
        created_ts = _clip_created_ts(clip)
        if not created_ts or now - created_ts <= retention_min * 60:
            continue
        old_path = os.path.join(clip_dir, safe_clip_id(clip.get("clip_id", "")))
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        clip["raw_clip_saved"] = False
        clip["raw_clip_expired"] = True
        clip["url"] = ""
    return clips


def save_clip(
    session_id: str,
    source_video_path: str,
    raw_emotion: str,
    display_emotion: str,
    person_check: dict | None,
    no_person: bool,
    emotion_structured: dict | None = None,
    media_signals: dict | None = None,
    force_save_raw_clip: bool = False,
) -> dict | None:
    if not source_video_path or not os.path.exists(source_video_path):
        return None
    safe_session = safe_session_id(session_id)
    clip_dir = emotion_clip_dir(safe_session)
    os.makedirs(clip_dir, exist_ok=True)
    stamp = int(time.time() * 1000)
    clip_id = f"{stamp}_{secrets.token_hex(4)}.webm"
    dest_path = os.path.join(clip_dir, clip_id)
    save_raw_clip = bool(force_save_raw_clip or config.get("PRIVACY_SAVE_RAW_CLIP", False))
    raw_clip_saved = False
    if save_raw_clip:
        try:
            shutil.copyfile(source_video_path, dest_path)
            raw_clip_saved = True
        except Exception as e:
            print(f"⚠️ 情緒影片片段保存失敗，改為只保存分析 metadata: {e}")

    clip = {
        "clip_id": clip_id,
        "session_id": safe_session,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "emotion": raw_emotion,
        "emotion_display": display_emotion,
        "emotion_label": (emotion_structured or {}).get("emotion_label", ""),
        "emotion_evidence": (emotion_structured or {}).get("emotion_evidence", ""),
        "emotion_distribution": (emotion_structured or {}).get("emotion_distribution", {}),
        "speech_text": (emotion_structured or {}).get("speech_text", ""),
        "media_signals": media_signals or (emotion_structured or {}).get("media_signals", {}),
        "no_person": bool(no_person),
        "person_detected": bool((person_check or {}).get("person_detected")),
        "person_hits": int((person_check or {}).get("person_hits") or (person_check or {}).get("face_hits") or 0),
        "face_hits": int((person_check or {}).get("face_hits") or (person_check or {}).get("person_hits") or 0),
        "frames_checked": int((person_check or {}).get("frames_checked") or 0),
        "detector": (person_check or {}).get("detector", ""),
        "boxes": (person_check or {}).get("boxes", []),
        "raw_clip_saved": raw_clip_saved,
        "raw_clip_retention_minutes": config.get("PRIVACY_RAW_CLIP_RETENTION_MINUTES", 10),
        "event_vector_only": bool(config.get("PRIVACY_STORE_EVENT_VECTOR_ONLY", True)),
        "url": f"/api/emotion_clips/{safe_session}/media/{clip_id}" if raw_clip_saved else "",
    }
    clips = _cleanup_expired_raw_clips(safe_session, load_clip_index(safe_session))
    clips.append(clip)
    max_clips = max(1, int(config.get("EMOTION_CLIP_MAX_PER_SESSION", 30)))
    while len(clips) > max_clips:
        old = clips.pop(0)
        old_path = os.path.join(clip_dir, safe_clip_id(old.get("clip_id", "")))
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    _save_clip_index(safe_session, clips)
    return clip


def delete_all_clips(session_id: str):
    safe_session = safe_session_id(session_id)
    clip_dir = emotion_clip_dir(safe_session)
    if os.path.exists(clip_dir):
        shutil.rmtree(clip_dir, True)
