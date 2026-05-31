from datetime import datetime


session_db = {}


def record_session_state(
    session_id: str,
    emotion: str = "",
    user_speech: str = "",
    ai_response: str = "",
    language: str = "",
):
    """記錄 5 秒一次的情緒，或語音對話紀錄"""
    if session_id not in session_db:
        session_db[session_id] = []

    record = {
        "timestamp": datetime.now().isoformat(),
        "emotion": emotion,
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
