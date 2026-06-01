import os
import json
import threading
import time
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 靜態與網路設定 (需寫在 .env)
# ==========================================
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
EMOTION_LLAMA_GRADIO_URL = os.getenv("EMOTION_LLAMA_GRADIO_URL", "http://127.0.0.1:7889")
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")
ENABLE_NGROK = os.getenv("ENABLE_NGROK", "true").lower() not in ("0", "false", "no", "off")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8001"))
DEMO_PUBLIC_MODE = os.getenv("DEMO_PUBLIC_MODE", "false")
POS_DEMO_TOKEN = os.getenv("POS_DEMO_TOKEN", "")
ADMIN_DEMO_TOKEN = os.getenv("ADMIN_DEMO_TOKEN", "")
WS_DEMO_TOKEN = os.getenv("WS_DEMO_TOKEN", "")
PUBLIC_POS_ORIGIN = os.getenv("PUBLIC_POS_ORIGIN", "")
PUBLIC_ADMIN_ORIGIN = os.getenv("PUBLIC_ADMIN_ORIGIN", "")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:8000,http://127.0.0.1:8001,http://localhost:8000,http://localhost:8001,http://0.0.0.0:8000,http://0.0.0.0:8001",
    ).split(",")
    if origin.strip()
]
for _public_origin in (PUBLIC_POS_ORIGIN, PUBLIC_ADMIN_ORIGIN):
    if _public_origin and _public_origin not in CORS_ORIGINS:
        CORS_ORIGINS.append(_public_origin)
MENU_JSON_PATH = "./menu_data/menu.json"
LEARNING_DATA_DIR = "./learning_data"
SETTINGS_JSON_PATH = "./learning_data/settings.json"
os.makedirs(LEARNING_DATA_DIR, exist_ok=True)

OLLAMA_TIMEOUT = 120

_settings_cache = None
_settings_mtime = None
_settings_last_check = 0.0
_settings_lock = threading.RLock()  # RLock allows re-entry from save_settings → load_settings

# ==========================================
# 動態設定管理器 (支援後台即時讀寫)
# ==========================================
DEFAULT_SETTINGS = {
    "DEMO_PUBLIC_MODE": DEMO_PUBLIC_MODE.lower() in ("1", "true", "yes", "on"),
    "MODEL_NAME": "qwen3.5:4b",
    "ENABLE_GEMINI_OPTIONS": False,
    "GEMINI_MODEL_NAME": "gemini-3-flash-preview",
    "GEMINI_COOLDOWN_SEC": 60,
    "GEMINI_NUM_PREDICT": 512,
    "GEMINI_USE_JSON_MIME": False,
    "ENABLE_DEBUG_ROUTES": False,
    "OLLAMA_TEMPERATURE": 0.8,
    "OLLAMA_NUM_PREDICT": 2048,
    "OLLAMA_LOG_RAW": False,
    "PRIVACY_STORE_EVENT_VECTOR_ONLY": True,
    # ── RAG ───────────────────────────────────────────────────────
    "RAG_ENABLED": True,                    # 預設開啟（無文件時自動跳過）
    "RAG_EMBEDDING_MODEL": "BAAI/bge-small-zh-v1.5",  # fastembed，支援中文，約 90MB
    "RAG_COLLECTION": "kiosk_rag",
    "RAG_TOP_K": 3,
    # ── 語音模型 ──────────────────────────────
    "VOICE_ASSIST_MODEL": "qwen3.5:4b",
    "VOICE_ASSIST_SYSTEM_PROMPT": "",       # 空字串 = 使用 voice_service 內建預設
    "VOICE_ASSIST_SYSTEM_PROMPT_EN": "",
    "AI_PUSH_SYSTEM_PROMPT": "",            # 空字串 = 使用 ai_push_service 內建預設
    # ── STT ───────────────────────────────────
    "STT_PROVIDER": "faster_whisper",       # "faster_whisper" | "openai_compatible"
    "STT_MODEL": "small",                   # faster_whisper: tiny/small/medium; openai_compat: "whisper-1"
    "STT_LANGUAGE": "zh",                   # "" = 自動偵測
    "STT_INITIAL_PROMPT": "麥當勞點餐，繁體中文，常見品項：大麥克、薯條、麥克雞塊、可樂、套餐、咖啡、拿鐵",
    "STT_API_URL": "https://api.openai.com",
    "STT_API_KEY": "",
    # ── TTS ───────────────────────────────────
    "TTS_PROVIDER": "melo",                 # "edge" | "melo" | "openai_compatible"
    "EDGE_TTS_VOICE": "zh-TW-HsiaoChenNeural",
    "EDGE_TTS_VOICE_EN": "en-US-JennyNeural",
    "TTS_SPEED": 1.0,                       # MeloTTS 語速
    "TTS_MODEL": "tts-1",                   # openai_compatible 模型名稱
    "TTS_VOICE": "alloy",                   # openai_compatible 聲音
    "TTS_API_URL": "https://api.openai.com",
    "TTS_API_KEY": "",
    # ── Emotion-LLaMA ─────────────────────────────────────────────
    "EMOTION_LLAMA_ENABLED": False,
    "EMOTION_LLAMA_CLIP_SEC": 2.0,
    "EMOTION_LLAMA_QUALITY_CHECK": True,
    "EMOTION_LLAMA_AFFECT_VOICE": False,
    "EMOTION_LLAMA_AFFECT_BARRIER": False,
    "EMOTION_LLAMA_PROMPT": (
        "The person in video says: {speech_text}\n"
        "[reason] What are the facial expressions, body language, gestures, and vocal tone "
        "used in the video? What is the intended meaning behind the words? Which emotion does "
        "this reflect? If the audio is quiet or there are few words, do not answer unable only "
        "because speech is limited; use visible facial expressions, subtle gestures, posture, "
        "and body language. If a person is visible but emotional cues are subtle, describe the "
        "most likely low-intensity emotional state and the evidence."
    ),
}

PUBLIC_SETTINGS_KEYS = {
    "DEMO_PUBLIC_MODE",
}


def _deep_merge(base: dict, override: dict) -> dict:
    """將 override 合併進 base；dict 型別的值遞迴合併，其餘直接覆蓋。"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def is_demo_public_mode() -> bool:
    env_value = str(os.getenv("DEMO_PUBLIC_MODE", DEMO_PUBLIC_MODE) or "").lower()
    if env_value in ("1", "true", "yes", "on"):
        return True
    try:
        return bool(load_settings().get("DEMO_PUBLIC_MODE", False))
    except Exception:
        return False

def load_settings():
    global _settings_cache, _settings_mtime, _settings_last_check

    now = time.time()
    try:
        current_mtime = os.path.getmtime(SETTINGS_JSON_PATH)
    except OSError:
        current_mtime = None

    # Fast path: no lock needed if cache is fresh
    if (
        _settings_cache is not None
        and current_mtime == _settings_mtime
        and now - _settings_last_check < 1.0
    ):
        return _settings_cache.copy()

    with _settings_lock:
        # Double-check after acquiring lock
        now = time.time()
        if (
            _settings_cache is not None
            and current_mtime == _settings_mtime
            and now - _settings_last_check < 1.0
        ):
            return _settings_cache.copy()

        if _settings_cache is not None and current_mtime == _settings_mtime:
            _settings_last_check = now
            return _settings_cache.copy()

        settings = DEFAULT_SETTINGS.copy()
        should_write = not os.path.exists(SETTINGS_JSON_PATH)

        if os.path.exists(SETTINGS_JSON_PATH):
            try:
                with open(SETTINGS_JSON_PATH, "r", encoding="utf-8") as f:
                    raw_settings = f.read().strip()
                    loaded_data = json.loads(raw_settings) if raw_settings else {}
                    if isinstance(loaded_data, dict):
                        settings = _deep_merge(settings, loaded_data)
                        should_write = any(key not in loaded_data for key in DEFAULT_SETTINGS) or any(
                            isinstance(DEFAULT_SETTINGS.get(k), dict) and
                            any(sk not in loaded_data.get(k, {}) for sk in DEFAULT_SETTINGS[k])
                            for k in DEFAULT_SETTINGS if isinstance(DEFAULT_SETTINGS.get(k), dict)
                        )
            except Exception as e:
                print(f"⚠️ Settings JSON 格式錯誤，將使用預設值覆寫: {e}")
                should_write = True

        if settings.get("ENABLE_GEMINI_OPTIONS") is not True:
            settings["AI_PROVIDER"] = "ollama"
            settings["QA_AI_PROVIDER"] = "ollama"

        if str(os.getenv("DEMO_PUBLIC_MODE", "")).lower() in ("1", "true", "yes", "on"):
            settings["DEMO_PUBLIC_MODE"] = True

        if should_write:
            try:
                tmp_path = SETTINGS_JSON_PATH + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(settings, f, ensure_ascii=False, indent=4)
                os.replace(tmp_path, SETTINGS_JSON_PATH)
                current_mtime = os.path.getmtime(SETTINGS_JSON_PATH)
            except Exception:
                pass

        _settings_cache = settings.copy()
        _settings_mtime = current_mtime
        _settings_last_check = now

        return settings.copy()


def load_public_settings():
    settings = load_settings()
    return {key: settings.get(key, DEFAULT_SETTINGS.get(key)) for key in PUBLIC_SETTINGS_KEYS}

def save_settings(new_settings):
    global _settings_cache, _settings_mtime, _settings_last_check
    with _settings_lock:
        settings = load_settings()
        settings.update(new_settings)
        tmp_path = SETTINGS_JSON_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, SETTINGS_JSON_PATH)
        _settings_cache = settings.copy()
        _settings_mtime = os.path.getmtime(SETTINGS_JSON_PATH)
        _settings_last_check = time.time()

def get(key, default=None):
    """供外部服務調用，動態獲取參數，並支援預設值防呆"""
    value = load_settings().get(key)
    if value is not None:
        return value
    return DEFAULT_SETTINGS.get(key, default)
