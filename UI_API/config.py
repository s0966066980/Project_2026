import os
import json
import time
from dotenv import load_dotenv
from prompts.defaults import (
    ASK_SYSTEM_PROMPT,
    ASK_SYSTEM_PROMPT_EN,
    CUSTOMER_SERVICE_SYSTEM_PROMPT,
    EMOTION_LLAMA_PROMPT,
    RECOMMEND_SYSTEM_PROMPT,
    RECOMMEND_SYSTEM_PROMPT_B,
)

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
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:8000,http://127.0.0.1:8001",
    ).split(",")
    if origin.strip()
]
VECTOR_DB_DIR = "./chroma_db"
MENU_JSON_PATH = "./menu_data/menu.json"
LEARNING_DATA_DIR = "./learning_data"
SETTINGS_JSON_PATH = "./learning_data/settings.json"
RAG_DOCS_JSON_PATH = "./learning_data/rag_docs.json"
RAG_REVIEW_LOG_PATH = "./learning_data/rag_review_logs.json"
RAG_VECTOR_META_PATH = "./learning_data/rag_vector_meta.json"
CUSTOMER_SERVICE_LOG_PATH = "./learning_data/customer_service_logs.json"
CUSTOMER_SERVICE_MEDIA_DIR = "./learning_data/customer_service_media"
EMOTION_ORDER_MEDIA_DIR = "./learning_data/emotion_order_media"

OLLAMA_TIMEOUT = 120
GEMINI_TIMEOUT = 120
EMOTION_LLAMA_TIMEOUT = 120

_settings_cache = None
_settings_mtime = None
_settings_last_check = 0.0

# ==========================================
# 動態設定管理器 (支援後台即時讀寫)
# ==========================================
DEFAULT_SETTINGS = {
    "AI_PROVIDER": "ollama",
    "QA_AI_PROVIDER": "ollama",
    "EMOTION_AI_PROVIDER": "ollama",
    "MODEL_NAME": "llama3.2",
    "ASK_MODEL_NAME": "llama3.2",
    "ENABLE_GEMINI_OPTIONS": False,
    "GEMINI_MODEL_NAME": "gemini-3-flash-preview",
    "GEMINI_FALLBACK_TO_OLLAMA": True,
    "GEMINI_COOLDOWN_SEC": 60,
    "GEMINI_NUM_PREDICT": 512,
    "GEMINI_USE_JSON_MIME": False,
    "CUSTOMER_SERVICE_MODE": "ollama",
    "EVENT_TRIGGERED_MULTIMODAL_ENABLED": True,
    "EMOTION_PERIODIC_ENABLED": False,
    "WHISPER_MODEL_SIZE": "base",
    "TTS_VOICE": "zh-TW-HsiaoChenNeural",
    "TTS_VOICE_EN": "en-US-JennyNeural",
    "OLLAMA_TEMPERATURE": 0.8,
    "OLLAMA_NUM_PREDICT": 2048,
    "RAG_TOP_K": 3,
    "rag": {
        "use_multi_query": True,
        "use_hybrid_search": True,
        "use_reranker": True,
        "use_context_compression": True,
        "use_answer_evaluation": True,
        "top_k_vector": 10,
        "top_k_keyword": 10,
        "top_k_final": 5,
        "context_max_chars": 2600,
        "chunk_size": 700,
        "chunk_overlap": 120,
        "embedding_provider": "ollama",
        "embedding_model": "nomic-embed-text",
        "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2"
    },
    "PERFORMANCE_MODE": "balanced",
    "EMOTION_PING_INTERVAL_SEC": 15,
    "EMOTION_RECORD_MS": 900,
    "RECOMMEND_INTERVAL_SEC": 30,
    "RECOMMEND_AFTER_ASK_DELAY_MS": 1200,
    "AUTO_RECOMMEND_MIN_GAP_SEC": 20,
    "EMOTION_MIN_GAP_SEC": 12,
    "CUSTOMER_EMOTION_WAIT_SEC": 8,
    "AB_SINGLE_CALL": True,
    "ENABLE_TTS_CACHE": True,
    "ENABLE_RECOMMEND_CACHE": True,
    "OLLAMA_LOG_RAW": False,
    "RAG_REVIEW_ENABLED": True,
    "INTERACTION_TRIGGER_THRESHOLD": 5,
    "INTERACTION_PRE_EVENT_BUFFER_SEC": 5,
    "INTERACTION_POST_EVENT_BUFFER_SEC": 5,
    "PRIVACY_SAVE_RAW_CLIP": False,
    "PRIVACY_RAW_CLIP_RETENTION_MINUTES": 10,
    "PRIVACY_STORE_EVENT_VECTOR_ONLY": True,
    "EMOTION_PERSON_CHECK_ENABLED": True,
    "EMOTION_PERSON_MIN_FACE_HITS": 1,
    "EMOTION_CLIP_MAX_PER_SESSION": 30,
    "YOLO_MODEL_PATH": "./models/yolo/yolo11n.pt",
    "YOLO_FRAME_INTERVAL_MS": 650,
    "YOLO_CONFIDENCE_THRESHOLD": 0.35,
    "YOLO_NMS_THRESHOLD": 0.4,
    "EMOTION_LLAMA_PREPROCESS_VIDEO": True,
    "EMOTION_LLAMA_MAX_VIDEO_SEC": 12,
    "EMOTION_LOW_AUDIO_DB": -45,
    "EMOTION_LLAMA_PROMPT": EMOTION_LLAMA_PROMPT,
    "RECOMMEND_SYSTEM_PROMPT": RECOMMEND_SYSTEM_PROMPT,
    "RECOMMEND_SYSTEM_PROMPT_B": RECOMMEND_SYSTEM_PROMPT_B,
    "ASK_SYSTEM_PROMPT": ASK_SYSTEM_PROMPT,
    "ASK_SYSTEM_PROMPT_EN": ASK_SYSTEM_PROMPT_EN,
    "CUSTOMER_SERVICE_SYSTEM_PROMPT": CUSTOMER_SERVICE_SYSTEM_PROMPT,
}

def load_settings():
    global _settings_cache, _settings_mtime, _settings_last_check

    os.makedirs(os.path.dirname(SETTINGS_JSON_PATH), exist_ok=True)
    now = time.time()
    try:
        current_mtime = os.path.getmtime(SETTINGS_JSON_PATH)
    except OSError:
        current_mtime = None

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
                loaded_data = json.load(f)
                if isinstance(loaded_data, dict):
                    settings.update(loaded_data)
                    should_write = any(key not in loaded_data for key in DEFAULT_SETTINGS)
        except Exception as e:
            print(f"Settings 讀取錯誤，將使用預設值覆寫: {e}")
            should_write = True

    if settings.get("ENABLE_GEMINI_OPTIONS") is not True:
        settings["AI_PROVIDER"] = "ollama"
        settings["QA_AI_PROVIDER"] = "ollama"
        settings["EMOTION_AI_PROVIDER"] = "ollama"
            
    if should_write:
        try:
            with open(SETTINGS_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            current_mtime = os.path.getmtime(SETTINGS_JSON_PATH)
        except Exception:
            pass

    _settings_cache = settings.copy()
    _settings_mtime = current_mtime
    _settings_last_check = now
        
    return settings.copy()

def save_settings(new_settings):
    global _settings_cache, _settings_mtime, _settings_last_check
    settings = load_settings()
    settings.update(new_settings)
    
    with open(SETTINGS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)
    _settings_cache = settings.copy()
    _settings_mtime = os.path.getmtime(SETTINGS_JSON_PATH)
    _settings_last_check = time.time()

def get(key, default=None):
    """供外部服務調用，動態獲取參數，並支援預設值防呆"""
    value = load_settings().get(key)
    if value is not None:
        return value
    return DEFAULT_SETTINGS.get(key, default)
