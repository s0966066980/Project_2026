from datetime import datetime


session_db = {}


def record_session_state(
    session_id: str,
    user_speech: str = "",
    ai_response: str = "",
    language: str = "",
    mentioned_ids: list | None = None,
    cart_actions: list | None = None,
):
    """記錄語音對話紀錄（含推薦 ID，供下一輪多輪記憶使用）"""
    if session_id not in session_db:
        session_db[session_id] = []

    record = {
        "timestamp": datetime.now().isoformat(),
        "user_speech": user_speech,
        "ai_response": ai_response,
        "language": language,
        "mentioned_ids": mentioned_ids or [],
        "cart_actions": cart_actions or [],
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
