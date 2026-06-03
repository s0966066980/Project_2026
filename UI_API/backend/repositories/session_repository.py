from datetime import datetime


session_db = {}


def record_session_state(
    session_id: str,
    user_speech: str = "",
    ai_response: str = "",
    language: str = "",
):
    """記錄語音對話紀錄"""
    if session_id not in session_db:
        session_db[session_id] = []

    record = {
        "timestamp": datetime.now().isoformat(),
        "user_speech": user_speech,
        "ai_response": ai_response,
        "language": language,
    }
    session_db[session_id].append(record)
    max_records = 80
    if len(session_db[session_id]) > max_records:
        session_db[session_id] = session_db[session_id][-max_records:]
    return record


def get_session_history(session_id: str):
    return session_db.get(session_id, [])


def archive_session(session_id: str):
    if session_id in session_db:
        del session_db[session_id]
    clear_session_mood(session_id)


# ── 心情評分儲存（與語音對話 session_db 分開） ──────────────────
_mood_db: dict[str, dict] = {}


def set_session_mood(session_id: str, mood_score: int, mood_label: str) -> None:
    _mood_db[session_id] = {"mood_score": mood_score, "mood_label": mood_label}


def get_session_mood(session_id: str) -> dict:
    return _mood_db.get(session_id, {"mood_score": 0, "mood_label": ""})


def clear_session_mood(session_id: str) -> None:
    _mood_db.pop(session_id, None)
