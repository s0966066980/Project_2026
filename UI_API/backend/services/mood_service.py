"""心情服務：從 session 讀取 mood_score，回傳對應 prompt context 字串。"""
import config
from repositories import session_repository

MOOD_LABELS: dict[int, str] = {
    1: "很差",
    2: "普通",
    3: "還不錯",
    4: "很開心",
    5: "超棒",
}


def get_mood_context(session_id: str) -> str:
    """回傳要注入 AI prompt 的心情描述字串；未選（score=0）回傳空字串。"""
    mood = session_repository.get_session_mood(session_id)
    score = mood.get("mood_score", 0)
    if not score:
        return ""
    return config.get(f"MOOD_CONTEXT_{score}", "")


def get_mood_label(score: int) -> str:
    return MOOD_LABELS.get(score, "")
