import os
import sys
import json
import threading
import time
from dotenv import load_dotenv

load_dotenv()

# prompt 預設值集中在 backend/prompts/defaults.py（確保該套件可匯入）
_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
from prompts import defaults as _prompts

# ==========================================
# 靜態與網路設定 (需寫在 .env)
# ==========================================
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL",
    OLLAMA_API_URL.split("/api/")[0] if "/api/" in OLLAMA_API_URL else "http://localhost:11434"
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
EMOTION_LLAMA_GRADIO_URL = os.getenv("EMOTION_LLAMA_GRADIO_URL", "http://127.0.0.1:7889")
R1_OMNI_GRADIO_URL = os.getenv("R1_OMNI_GRADIO_URL", "http://127.0.0.1:7890")
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
        "http://127.0.0.1:9000,http://127.0.0.1:9001,http://localhost:9000,http://localhost:9001,http://0.0.0.0:9000,http://0.0.0.0:9001",
    ).split(",")
    if origin.strip()
]
for _public_origin in (PUBLIC_POS_ORIGIN, PUBLIC_ADMIN_ORIGIN):
    if _public_origin and _public_origin not in CORS_ORIGINS:
        CORS_ORIGINS.append(_public_origin)
MENU_JSON_PATH = "./menu_data/menu.json"
LEARNING_DATA_DIR = "./learning_data"
SETTINGS_JSON_PATH = "./learning_data/settings.json"
RAG_DOCUMENTS_DIR = "./rag_documents"
os.makedirs(LEARNING_DATA_DIR, exist_ok=True)

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
    "OLLAMA_TIMEOUT": 120,           # HTTP 請求 timeout（秒），熱改有效
    "OLLAMA_POOL_CONNECTIONS": 2,    # 連線池數量（需重啟生效）
    "OLLAMA_POOL_MAXSIZE": 4,        # 連線池最大連線數（需重啟生效）
    "PRIVACY_STORE_EVENT_VECTOR_ONLY": True,
    # ── 會員制 ─────────────────────────────────────────────────────
    "MEMBER_ENABLED": True,            # 總開關；false 時 kiosk 跳過選擇頁、後台隱藏分頁
    "MEMBER_USUALS_COUNT": 8,          # 「您的常點」顯示品項數
    "MEMBER_PUSH_WEIGHT": 4,           # 會員常點品項於 ai_push 加權倍率
    "MEMBER_ORDERS_KEEP": 20,          # 每位會員保留近期訂單筆數
    # ── RAG ───────────────────────────────────────────────────────
    "RAG_ENABLED": True,                    # 預設開啟（無文件時自動跳過）
    "RAG_EMBEDDING_MODEL": "BAAI/bge-small-zh-v1.5",  # fastembed，支援中文，約 90MB
    "RAG_COLLECTION": "kiosk_rag",
    "RAG_TOP_K": 3,
    # ── 語音模型 ──────────────────────────────
    "VOICE_ASSIST_MODEL": "qwen3.5:4b",
    "VOICE_HISTORY_MAX_TURNS": 4,           # 注入 LLM 的對話歷史輪數
    "VOICE_ASSIST_SYSTEM_PROMPT": _prompts.VOICE_ASSIST_SYSTEM_PROMPT,
    "VOICE_ASSIST_SYSTEM_PROMPT_EN": _prompts.VOICE_ASSIST_SYSTEM_PROMPT_EN,
    "AI_PUSH_SYSTEM_PROMPT": _prompts.AI_PUSH_SYSTEM_PROMPT,
    # ── AI 推播 / 前端行為 ────────────────────
    "AI_PUSH_TEXT_MIN": 18,                 # push_text 最少字數
    "AI_PUSH_TEXT_MAX": 34,                 # push_text 最多字數
    "AI_PUSH_REFRESH_SEC": 15,              # 推播欄刷新間隔（秒）
    "PASSIVE_VOICE_KEYWORDS": ["找不到", "在哪裡", "哪邊有", "哪裡有", "哪裡可以"],
    "PASSIVE_VOICE_ALIASES": {},   # {"MCDxxx": ["別名1", "別名2"]}
    "AI_PUSH_PRIORITY_CATS": [       # 優先推播分類，熱改有效
        "超值全餐", "極選系列", "點心", "飲料", "麥當勞分享盒"
    ],
    # ── 語音菜單快取 ──────────────────────────
    "VOICE_MENU_CACHE_TTL_SEC": 60.0,       # 菜單資料快取 TTL（秒）
    # ── STT ───────────────────────────────────
    "STT_PROVIDER": "faster_whisper",       # "faster_whisper" | "openai_compatible"
    "STT_MODEL": "small",                   # faster_whisper: tiny/small/medium; openai_compat: "whisper-1"
    "STT_LANGUAGE": "zh",                   # "" = 自動偵測
    "STT_INITIAL_PROMPT": "麥當勞點餐，繁體中文，常見品項：大麥克、薯條、麥克雞塊、可樂、套餐、咖啡、拿鐵",
    "STT_API_URL": "https://api.openai.com",
    "STT_API_KEY": "",
    "STT_HTTP_TIMEOUT_SEC": 30,             # HTTP STT API 請求 timeout（秒）
    # ── TTS ───────────────────────────────────
    "TTS_PROVIDER": "edge",                 # "edge" | "melo" | "openai_compatible"
    "EDGE_TTS_VOICE": "zh-TW-HsiaoChenNeural",
    "EDGE_TTS_VOICE_EN": "en-US-JennyNeural",
    "TTS_SPEED": 1.0,                       # MeloTTS 語速
    "TTS_MODEL": "tts-1",                   # openai_compatible 模型名稱
    "TTS_VOICE": "alloy",                   # openai_compatible 聲音
    "TTS_API_URL": "https://api.openai.com",
    "TTS_API_KEY": "",
    "TTS_HTTP_TIMEOUT_SEC": 30,             # HTTP TTS API 請求 timeout（秒）
    # ── 情緒分析 ─────────────────────────────────────────────
    "EMOTION_PROVIDER": "emotion_llama",    # "emotion_llama"（:7889）| "r1_omni"（:7890）
    "EMOTION_LLAMA_ENABLED": False,
    "EMOTION_LLAMA_CLIP_SEC": 2.0,
    "PAYMENT_EMOTION_CLIP_SEC": 5.0,   # 付款倒數逾時擷取秒數（觸發點 = 15 - 此值）
    "EMOTION_LLAMA_TIMEOUT_SEC": 120,       # HTTP 請求 timeout（秒）
    "EMOTION_LLAMA_QUALITY_CHECK": True,
    "EMOTION_LLAMA_AFFECT_VOICE": False,
    "EMOTION_LLAMA_AFFECT_BARRIER": False,
    "EMOTION_LLAMA_EVENT_VOICE":        False,   # 語音模式結束後觸發分析
    "EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT": True,  # 付款倒數逾時觸發分析（預設開啟）
    "EMOTION_LLAMA_VOICE_WAIT_MODE":    "speed", # "speed"=速度優先 / "analysis"=分析模式
    "EMOTION_LLAMA_PROMPT": _prompts.EMOTION_LLAMA_PROMPT,
    "EMOTION_LLAMA_PROMPT_MAX_CHARS": 800,
    # ── 互動障礙偵測閾值 ──────────────────────
    "BARRIER_DWELL_TIMEOUT_SEC": 40,        # 選單頁停留超過此秒數視為 menu_hesitation
    "BARRIER_CATEGORY_SWITCH_MAX": 4,       # 分類切換次數達此值視為 menu_hesitation
    "BARRIER_CART_REMOVE_MAX": 2,           # 購物車移除次數達此值視為 menu_hesitation
    "BARRIER_PAYMENT_FAIL_MAX": 1,          # 付款失敗次數達此值視為 payment_confusion
    # ── 機台識別 ─────────────────────────────────────────────────
    "KIOSK_NAME": "機台01",
    # ── 付款逾時協助 Prompt ───────────────────────────────────────
    "PAYMENT_ASSIST_PROMPT": _prompts.PAYMENT_ASSIST_PROMPT,
}

PUBLIC_SETTINGS_KEYS = {
    "DEMO_PUBLIC_MODE",
    "EMOTION_LLAMA_ENABLED",
    "EMOTION_LLAMA_CLIP_SEC",
    "EMOTION_LLAMA_EVENT_VOICE",        # POS 需要：控制語音模式結束後是否觸發分析
    "EMOTION_LLAMA_VOICE_WAIT_MODE",    # POS 需要：speed / analysis 兩種等待模式
    "EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT",  # POS 需要：控制付款倒數逾時是否觸發分析
    "AI_PUSH_REFRESH_SEC",
    "PAYMENT_EMOTION_CLIP_SEC",
    "PASSIVE_VOICE_KEYWORDS",
    "MEMBER_ENABLED",
    "MEMBER_USUALS_COUNT",
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
    if value is not None and value != "":
        return value
    return DEFAULT_SETTINGS.get(key, default)
