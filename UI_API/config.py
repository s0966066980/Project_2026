import json
import os
import sys
import threading
import time
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
REPOSITORY_DIR = os.path.dirname(PROJECT_DIR)

# Load both supported local env locations deterministically. UI_API/.env keeps
# compatibility precedence; an explicit repository-external deployment file
# can provide one complete Pilot contract without copying secrets into Git.
_external_env_file = str(os.getenv("PROJECT_2026_ENV_FILE", "") or "").strip()
if _external_env_file:
    _external_env_path = Path(_external_env_file).expanduser()
    if not _external_env_path.is_file():
        raise RuntimeError(f"PROJECT_2026_ENV_FILE does not exist: {_external_env_path}")
    load_dotenv(_external_env_path, override=False)
load_dotenv(os.path.join(PROJECT_DIR, ".env"))
load_dotenv(os.path.join(REPOSITORY_DIR, ".env"))


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return default


APP_ENV = os.getenv("APP_ENV", "development").strip().lower() or "development"
SECURITY_ENFORCED = _env_bool("SECURITY_ENFORCED", APP_ENV in ("production", "staging"))
ALLOW_UNSAFE_PRODUCTION_ROUTES = _env_bool("ALLOW_UNSAFE_PRODUCTION_ROUTES", False)
ALLOW_POSTGRES_JSON_FALLBACK = _env_bool("ALLOW_POSTGRES_JSON_FALLBACK", False)
MEMBER_IDENTITY_READ_MODE = os.getenv("MEMBER_IDENTITY_READ_MODE", "legacy").strip().lower() or "legacy"
MEMBER_IDENTITY_DUAL_WRITE = _env_bool("MEMBER_IDENTITY_DUAL_WRITE", False)
REDIS_URL = os.getenv("REDIS_URL", "").strip()
SHARED_RATE_LIMIT_ENABLED = _env_bool("SHARED_RATE_LIMIT_ENABLED", APP_ENV in ("production", "staging"))


KNOWN_APP_ENVS = frozenset({"development", "test", "staging", "pilot", "production"})


def is_production() -> bool:
    return APP_ENV == "production"


def is_commercial_runtime() -> bool:
    """Staging, pilot and production require commercial fail-closed configuration."""

    return APP_ENV in {"staging", "pilot", "production"}


def is_security_enforced() -> bool:
    return bool(SECURITY_ENFORCED or APP_ENV in ("production", "staging", "pilot"))


def _token_configured(value: str) -> bool:
    return bool(str(value or "").strip())


def _looks_like_placeholder_secret(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    placeholders = (
        "change_me",
        "changeme",
        "replace_me",
        "todo",
        "placeholder",
        "demo",
        "secret",
        "password",
        "admin",
        "test",
    )
    return normalized in placeholders or normalized.startswith("change_me")


def validate_startup_config() -> None:
    """Fail fast for unsafe commercial runtime configuration (staging/pilot/production)."""
    if APP_ENV not in KNOWN_APP_ENVS:
        raise RuntimeError(f"Unknown APP_ENV '{APP_ENV}'. Expected one of: {', '.join(sorted(KNOWN_APP_ENVS))}")
    from modules.runtime_persistence import PersistenceConfigurationError, adapter_coverage
    from modules.runtime_persistence.runtime import current_profile

    try:
        persistence = current_profile(app_env=APP_ENV)
        persistence.runtime_paths.ensure()
    except PersistenceConfigurationError as exc:
        raise RuntimeError(f"Invalid Runtime Persistence Profile: {exc}") from exc
    coverage = adapter_coverage(persistence.backend)
    if not coverage["complete"] and APP_ENV != "test":
        missing = ", ".join(coverage["missing"])
        raise RuntimeError(f"Runtime persistence adapter coverage is incomplete: {missing}")
    if not is_commercial_runtime():
        return
    label = APP_ENV
    errors: list[str] = []
    if _external_env_file and _external_env_path.stat().st_mode & 0o077:
        errors.append("PROJECT_2026_ENV_FILE must use private file permissions (0600)")
    if not is_security_enforced():
        errors.append(f"SECURITY_ENFORCED must be true in {label}")
    if APP_ENV == "pilot" and ENABLE_NGROK:
        errors.append("ENABLE_NGROK must be false for the local-pilot HTTP deployment")
    if ADMIN_LOCAL_MANAGER_AUTH_ENABLED:
        errors.append("ADMIN_LOCAL_MANAGER_AUTH_ENABLED is development-only and must be false in commercial runtime")
    if ENABLE_LEGACY_KIOSK_TOKEN and not _token_configured(KIOSK_DEVICE_TOKEN):
        errors.append("KIOSK_DEVICE_TOKEN must be configured when legacy Kiosk authentication is enabled")
    if not _token_configured(os.getenv("ADMIN_MEMBER_REF_SECRET", "")):
        errors.append(f"ADMIN_MEMBER_REF_SECRET must be configured in {label}")
    elif _looks_like_placeholder_secret(os.getenv("ADMIN_MEMBER_REF_SECRET", "")):
        errors.append("ADMIN_MEMBER_REF_SECRET must not use a placeholder/default secret")
    if _env_bool("ALLOW_POSTGRES_JSON_FALLBACK", False):
        errors.append(f"ALLOW_POSTGRES_JSON_FALLBACK must be false in {label}")
    if str(os.getenv("STRUCTURED_LOGGING_ENABLED", "true")).strip().lower() not in {"1", "true", "yes", "on"}:
        errors.append(f"STRUCTURED_LOGGING_ENABLED must be true in {label}")
    try:
        if int(os.getenv("LOG_RETENTION_DAYS", "90")) <= 0:
            errors.append(f"LOG_RETENTION_DAYS must be positive in {label}")
    except ValueError:
        errors.append("LOG_RETENTION_DAYS must be a valid integer")
    if persistence.backend != "postgresql":
        errors.append(f"DATABASE_BACKEND must be postgresql in {label}")
    if not persistence.database_url:
        errors.append(f"DATABASE_URL or DATABASE_URL_FILE must be configured in {label}")
    if label == "production" and not bool(persistence.endpoint_summary().get("tls_requested")):
        errors.append("Production PostgreSQL must request TLS using sslmode")
    shared_rate_default = APP_ENV in {"production", "staging"}
    if _env_bool("SHARED_RATE_LIMIT_ENABLED", shared_rate_default) and not _token_configured(
        os.getenv("REDIS_URL", "")
    ):
        errors.append(f"REDIS_URL must be configured when shared {label} rate limiting is enabled")
    if MEMBER_IDENTITY_READ_MODE not in {"legacy", "dual", "uuid_preferred", "uuid_only"}:
        errors.append("MEMBER_IDENTITY_READ_MODE is invalid")
    if not _token_configured(os.getenv("OBJECT_STORAGE_SIGNING_SECRET", "")):
        errors.append(f"OBJECT_STORAGE_SIGNING_SECRET must be configured in {label}")
    elif _looks_like_placeholder_secret(os.getenv("OBJECT_STORAGE_SIGNING_SECRET", "")):
        errors.append("OBJECT_STORAGE_SIGNING_SECRET must not use a placeholder/default secret")
    object_storage_backend = str(os.getenv("OBJECT_STORAGE_BACKEND", "local") or "local").strip().lower()
    if object_storage_backend in {"memory", "inmemory", "test"}:
        errors.append(f"OBJECT_STORAGE_BACKEND must not be memory/test in {label}")
    if MEMBER_IDENTITY_READ_MODE != "legacy" or MEMBER_IDENTITY_DUAL_WRITE:
        if not _token_configured(os.getenv("MEMBER_PHONE_KEY_VERSION", "")):
            errors.append("Member PII key version must be configured")
        has_lookup_material = _token_configured(os.getenv("MEMBER_PHONE_LOOKUP_PEPPERS_JSON", "")) or _token_configured(
            os.getenv("MEMBER_PHONE_LOOKUP_PEPPER", "")
        )
        has_encryption_material = _token_configured(
            os.getenv("MEMBER_PHONE_ENCRYPTION_KEYS_JSON", "")
        ) or _token_configured(os.getenv("MEMBER_PHONE_ENCRYPTION_KEY", ""))
        if not has_lookup_material or not has_encryption_material:
            errors.append("Member PII key material must be configured")
    for scope_key in ("DEFAULT_TENANT_ID", "DEFAULT_STORE_ID", "DEFAULT_DEVICE_ID"):
        scope_value = str(os.getenv(scope_key, "") or "").strip()
        if not scope_value:
            errors.append(f"{scope_key} must be configured in {label}")
            continue
        try:
            UUID(scope_value)
        except ValueError:
            errors.append(f"{scope_key} must be a valid UUID")
    if "*" in CORS_ORIGINS:
        errors.append(f"CORS_ORIGINS must not contain wildcard '*' in {label}")
    if not ALLOW_UNSAFE_PRODUCTION_ROUTES:
        if _env_bool("ENABLE_DEMO_ROUTES", False):
            errors.append(f"ENABLE_DEMO_ROUTES must be false in {label}")
        if _env_bool("ENABLE_DIAGNOSTIC_ROUTES", False):
            errors.append(f"ENABLE_DIAGNOSTIC_ROUTES must be false in {label}")
        if _env_bool("ENABLE_DEBUG_ROUTES", False):
            errors.append(f"ENABLE_DEBUG_ROUTES must be false in {label}")
    if errors:
        raise RuntimeError(f"Unsafe {label} configuration: " + "; ".join(errors))

# prompt 預設值集中在 backend/prompts/defaults.py（確保該套件可匯入）
_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
from modules.runtime_persistence import configured_runtime_paths  # noqa: E402
from prompts import defaults as _prompts  # noqa: E402

_RUNTIME_PATHS = configured_runtime_paths(os.environ, repository_root=Path(REPOSITORY_DIR))

# ==========================================
# 靜態與網路設定 (需寫在 .env)
# ==========================================
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL",
    OLLAMA_API_URL.split("/api/")[0] if "/api/" in OLLAMA_API_URL else "http://localhost:11434"
)
# Provider credentials live only in the environment: they must never enter the settings
# document, which is versioned, scoped, and broadcast to connected clients.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_API_BASE_URL = os.getenv("NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1")
STT_API_KEY = os.getenv("STT_API_KEY", "")
TTS_API_KEY = os.getenv("TTS_API_KEY", "")
CREDENTIAL_SETTING_KEYS = frozenset({
    "NVIDIA_API_KEY",
    "STT_API_KEY",
    "TTS_API_KEY",
})
R1_OMNI_GRADIO_URL = os.getenv("R1_OMNI_GRADIO_URL", "http://127.0.0.1:7890")
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")
ENABLE_NGROK = os.getenv("ENABLE_NGROK", "true").lower() not in ("0", "false", "no", "off")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8001"))
DEMO_PUBLIC_MODE = os.getenv("DEMO_PUBLIC_MODE", "false")
POS_DEMO_TOKEN = os.getenv("POS_DEMO_TOKEN", "")
WS_DEMO_TOKEN = os.getenv("WS_DEMO_TOKEN", "")
KIOSK_DEVICE_TOKEN = os.getenv("KIOSK_DEVICE_TOKEN", POS_DEMO_TOKEN)
ENABLE_LEGACY_KIOSK_TOKEN = _env_bool("ENABLE_LEGACY_KIOSK_TOKEN", not is_production())
ADMIN_SESSION_COOKIE_NAME = os.getenv("ADMIN_SESSION_COOKIE_NAME", "admin_session")
ADMIN_SESSION_TTL_SEC = int(os.getenv("ADMIN_SESSION_TTL_SEC", "28800"))
ADMIN_LOCAL_MANAGER_AUTH_ENABLED = _env_bool("ADMIN_LOCAL_MANAGER_AUTH_ENABLED", False)
ADMIN_MANAGER_LOGIN_IDENTITY = os.getenv("ADMIN_MANAGER_LOGIN_IDENTITY", "admin").strip() or "admin"
ADMIN_MANAGER_PASSWORD = os.getenv("ADMIN_MANAGER_PASSWORD", "")
ADMIN_MANAGER_IDLE_TIMEOUT_SEC = int(os.getenv("ADMIN_MANAGER_IDLE_TIMEOUT_SEC", "1800"))
DEVICE_SESSION_COOKIE_NAME = os.getenv("DEVICE_SESSION_COOKIE_NAME", "kiosk_device_session")
DEVICE_SESSION_TTL_SEC = int(os.getenv("DEVICE_SESSION_TTL_SEC", "3600"))
DEVICE_CREDENTIAL_TTL_DAYS = int(os.getenv("DEVICE_CREDENTIAL_TTL_DAYS", "90"))
DEVICE_CREDENTIAL_ROTATION_GRACE_SEC = int(os.getenv("DEVICE_CREDENTIAL_ROTATION_GRACE_SEC", "300"))
DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "")
DEFAULT_STORE_ID = os.getenv("DEFAULT_STORE_ID", "")
DEFAULT_DEVICE_ID = os.getenv("DEFAULT_DEVICE_ID", "")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "10485760"))
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
MENU_JSON_PATH = os.getenv("MENU_JSON_PATH", os.path.join(PROJECT_DIR, "menu_data", "menu.json"))
LEARNING_DATA_DIR = os.getenv("LEARNING_DATA_DIR", str(_RUNTIME_PATHS.exports))
SETTINGS_JSON_PATH = os.getenv("SETTINGS_JSON_PATH", os.path.join(LEARNING_DATA_DIR, "settings.json"))
RAG_DOCUMENTS_DIR = os.getenv("RAG_DOCUMENTS_DIR") or str(_RUNTIME_PATHS.imports)
_rag_chroma_dir = os.getenv("RAG_CHROMA_DIR") or str(_RUNTIME_PATHS.rag_indexes)
RAG_CHROMA_DIR = _rag_chroma_dir if os.path.isabs(_rag_chroma_dir) else os.path.join(PROJECT_DIR, _rag_chroma_dir)
RAG_COLLECTION = os.getenv("RAG_COLLECTION") or "kiosk_rag"
os.makedirs(LEARNING_DATA_DIR, exist_ok=True)

_settings_cache = None
_settings_mtime = None
_settings_last_check = 0.0
_settings_lock = threading.RLock()  # RLock allows re-entry from save_settings → load_settings

# ==========================================
# 動態設定管理器 (支援後台即時讀寫)
# ==========================================
DEFAULT_SETTINGS = {
    "APP_ENV": APP_ENV,
    "SECURITY_ENFORCED": SECURITY_ENFORCED,
    "DEMO_PUBLIC_MODE": DEMO_PUBLIC_MODE.lower() in ("1", "true", "yes", "on"),
    "MODEL_NAME": "qwen3.5:4b",
    # 文字模型選路：策略決定本機／雲端的先後與是否允許對外，雲端提供者決定 chain 裡的雲端那一段。
    "LLM_ROUTING_POLICY": "local_first",    # local_first | cloud_first | local_only | cloud_only
    # NVIDIA NIM is the sole cloud text provider; its API key/base URL live only in the
    # environment (NVIDIA_API_KEY / NVIDIA_API_BASE_URL), never in this settings document.
    "NIM_MODEL_NAME": "meta/llama-3.1-8b-instruct",
    "NIM_VOICE_MODEL": "meta/llama-3.1-8b-instruct",
    # Admin-added model IDs not in the built-in NIM Model Catalog (see NIM_TEXT_MODEL_CATALOG /
    # NIM_VOICE_MODEL_CATALOG below), appended to their respective dropdowns once saved.
    "NIM_CUSTOM_TEXT_MODELS": [],
    "NIM_CUSTOM_VOICE_MODELS": [],
    "ENABLE_DEBUG_ROUTES": False,
    "ENABLE_DEMO_ROUTES": _env_bool("ENABLE_DEMO_ROUTES", not is_production()),
    "ENABLE_DIAGNOSTIC_ROUTES": _env_bool("ENABLE_DIAGNOSTIC_ROUTES", not is_production()),
    "MAX_UPLOAD_BYTES": MAX_UPLOAD_BYTES,
    "RATE_LIMIT_ENABLED": _env_bool("RATE_LIMIT_ENABLED", True),
    "RATE_LIMIT_DEFAULT_PER_MINUTE": int(os.getenv("RATE_LIMIT_DEFAULT_PER_MINUTE", "120")),
    "STRUCTURED_LOGGING_ENABLED": _env_bool("STRUCTURED_LOGGING_ENABLED", True),
    "LOG_RETENTION_DAYS": int(os.getenv("LOG_RETENTION_DAYS", "90")),
    "OLLAMA_TEMPERATURE": 0.8,
    "OLLAMA_NUM_PREDICT": 2048,
    "OLLAMA_LOG_RAW": False,
    "OLLAMA_TIMEOUT": 120,           # HTTP 請求 timeout（秒），熱改有效
    "OLLAMA_KEEP_ALIVE": "30m",      # 模型閒置保留時間，避免首位顧客承擔冷載入
    "OLLAMA_POOL_CONNECTIONS": 2,    # 連線池數量（需重啟生效）
    "OLLAMA_POOL_MAXSIZE": 4,        # 連線池最大連線數（需重啟生效）
    "PRIVACY_STORE_EVENT_VECTOR_ONLY": True,
    # ── 會員制 ─────────────────────────────────────────────────────
    "MEMBER_ENABLED": True,            # 總開關；false 時 kiosk 跳過選擇頁、後台隱藏分頁
    "MEMBER_USUALS_COUNT": 8,          # 「您的常點」顯示品項數
    "MEMBER_PUSH_WEIGHT": 4,           # 會員常點品項於 ai_push 加權倍率
    "MEMBER_ORDERS_KEEP": 20,          # 每位會員保留近期訂單筆數
    "MEMBER_RECENT_ITEMS_KEEP": 20,     # 會員近期偏好品項保留數
    "RECOMMENDATION_CATEGORY_WEIGHT": 3, # 會員偏好分類加權
    "RECOMMENDATION_PAIR_WEIGHT": 5,    # 會員常見搭配加權
    "RECOMMENDATION_RAG_OFFER_WEIGHT": 4, # RAG 活動指定品項加權
    "RECOMMENDATION_RAG_CATEGORY_WEIGHT": 2, # RAG 活動分類加權
    "PROMOTION_DEFAULT_TIMEZONE": "Asia/Taipei", # 結構化活動預設門市時區
    "RECOMMENDATION_IGNORE_FEEDBACK_ENABLED": True, # 近期忽略事件回饋推薦引擎
    "RECOMMENDATION_IGNORE_WINDOW_MINUTES": 45,     # 忽略事件短期降權時間窗
    "RECOMMENDATION_FEEDBACK_EVENT_LIMIT": 500,     # 讀取近期推薦事件筆數
    "RECOMMENDATION_IGNORED_ITEM_PENALTY": 2,       # 忽略品項扣分
    "RECOMMENDATION_IGNORED_OFFER_PENALTY": 1,      # 忽略 offer 扣分
    "RECOMMENDATION_IGNORED_ITEM_EXCLUDE_THRESHOLD": 3, # 同品項忽略達門檻時短期排除
    "RECOMMENDATION_AVAILABILITY_ENABLED": True,    # 店鋪供應狀態影響推薦候選
    "RECOMMENDATION_LOW_STOCK_PENALTY": 1,          # 低庫存品項推薦降權
    "RECOMMENDATION_EXPERIMENT_ENABLED": False,     # 推薦策略 A/B testing 需由管理者明確啟用
    "RECOMMENDATION_EXPERIMENT_CONFIGURED": False,  # 區分管理者設定與舊版本自動寫入的 enabled
    "RECOMMENDATION_EXPERIMENT_ID": "recommendation_strategy_v1",
    "RECOMMENDATION_EXPERIMENT_VARIANTS": [
        {"variant_id": "control", "strategy": "weighted_random", "traffic": 50},
        {"variant_id": "ranked", "strategy": "ranked_top_score", "traffic": 50},
    ],
    "RECOMMENDATION_PURCHASE_RATE_TARGET": 0.10,  # 主管設定：有效曝光後確認購買率
    "RECOMMENDATION_IGNORE_RATE_GUARDRAIL": 0.35,  # 主管設定：有效曝光忽略率警戒值
    "DATABASE_BACKEND": os.getenv("DATABASE_BACKEND", "postgresql"),
    "DATABASE_TOPOLOGY": os.getenv("DATABASE_TOPOLOGY", "single"),
    "DATABASE_URL": os.getenv("DATABASE_URL", ""),
    "MEMBER_SESSION_TTL_SEC": int(os.getenv("MEMBER_SESSION_TTL_SEC", "86400")),
    "ENABLE_MEMBER_DUAL_WRITE": os.getenv("ENABLE_MEMBER_DUAL_WRITE", "false").lower() in ("1", "true", "yes", "on"),
    "ADMIN_MEMBER_REF_SECRET": os.getenv("ADMIN_MEMBER_REF_SECRET", ""),
    "ADMIN_AUDIT_MAX_RECORDS": int(os.getenv("ADMIN_AUDIT_MAX_RECORDS", "5000")),
    "MEMBER_CONSENT_VERSION": os.getenv("MEMBER_CONSENT_VERSION", "2026-07-phone-login-v1"),
    "MEMBER_PRIVACY_VERSION": os.getenv("MEMBER_PRIVACY_VERSION", "2026-07-privacy-v1"),
    "MEMBER_DATA_RETENTION_DAYS": int(os.getenv("MEMBER_DATA_RETENTION_DAYS", "730")),
    # ── RAG ───────────────────────────────────────────────────────
    "RAG_ENABLED": True,                    # 預設開啟（無文件時自動跳過）
    "RAG_EMBEDDING_MODEL": "BAAI/bge-small-zh-v1.5",  # fastembed，支援中文，約 90MB
    "RAG_COLLECTION": RAG_COLLECTION,
    "RAG_STRATEGY": "hybrid",             # "dense" | "bm25" | "hybrid"
    "RAG_TOP_K": 3,
    "RAG_ALERT_MAX_RECORDS": int(os.getenv("RAG_ALERT_MAX_RECORDS", "1000")),
    "RAG_ALERT_WEBHOOK_ENABLED": os.getenv("RAG_ALERT_WEBHOOK_ENABLED", "false").lower() in ("1", "true", "yes", "on"),
    "RAG_ALERT_WEBHOOK_URL": os.getenv("RAG_ALERT_WEBHOOK_URL", ""),
    "RAG_ALERT_WEBHOOK_TOKEN": os.getenv("RAG_ALERT_WEBHOOK_TOKEN", ""),
    "RAG_ALERT_WEBHOOK_TIMEOUT_SEC": float(os.getenv("RAG_ALERT_WEBHOOK_TIMEOUT_SEC", "5")),
    # ── 語音模型 ──────────────────────────────
    "VOICE_ASSIST_MODEL": "qwen3.5:4b",
    "VOICE_LLM_PREWARM_ENABLED": True,
    "VOICE_HISTORY_MAX_TURNS": 4,           # 注入 LLM 的對話歷史輪數
    "VOICE_ASSIST_SYSTEM_PROMPT": _prompts.VOICE_ASSIST_SYSTEM_PROMPT,
    "AI_PUSH_SYSTEM_PROMPT": _prompts.AI_PUSH_SYSTEM_PROMPT,
    # ── AI 推播 / 前端行為 ────────────────────
    "AI_PUSH_TEXT_MIN": 18,                 # 推薦詞最少字數（Admin 產生推薦詞時遵守）
    "AI_PUSH_TEXT_MAX": 34,                 # 推薦詞最多字數（Admin 產生推薦詞時遵守）
    "AI_PUSH_REFRESH_SEC": 15,              # 推播欄刷新間隔（秒）
    # 推播範圍是「哪些品項有資格被推播」的過濾器；排序仍由推薦引擎負責。
    "AI_PUSH_SCOPE_MODE": "all",            # all | categories | new_items | popular
    "AI_PUSH_SCOPE_CATEGORIES": [],         # AI_PUSH_SCOPE_MODE 為 categories 時生效
    "AI_PUSH_EXCLUDE_SEEN": True,           # 「換一個」累積排除本次已看過的品項
    "AI_PUSH_PREFETCH": True,               # 預先取回候選，讓「換一個」不必等待
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
    "STT_INITIAL_PROMPT": "麥當勞點餐，繁體中文，常見品項：大麥克、薯條、麥克雞塊、可樂、套餐、咖啡、拿鐵",
    "STT_API_URL": "https://api.openai.com",
    "STT_HTTP_TIMEOUT_SEC": 30,             # HTTP STT API 請求 timeout（秒）
    # ── TTS ───────────────────────────────────
    "TTS_PROVIDER": "edge",                 # "edge" | "melo" | "openai_compatible"
    "EDGE_TTS_VOICE": "zh-TW-HsiaoChenNeural",
    "TTS_SPEED": 1.0,                       # MeloTTS 語速
    "TTS_MODEL": "tts-1",                   # openai_compatible 模型名稱
    "TTS_VOICE": "alloy",                   # openai_compatible 聲音
    "TTS_API_URL": "https://api.openai.com",
    "TTS_HTTP_TIMEOUT_SEC": 30,             # HTTP TTS API 請求 timeout（秒）
    # ── 情緒分析 ─────────────────────────────────────────────
    "EMOTION_ENABLED": False,
    "EMOTION_CLIP_SEC": 2.0,
    "EMOTION_TIMEOUT_SEC": 120,       # HTTP 請求 timeout（秒）
    "EMOTION_QUALITY_CHECK": True,
    "EMOTION_AFFECT_VOICE": False,
    "EMOTION_ASSISTANCE_MODE": "shadow",     # disabled | shadow | active
    "EMOTION_ASSISTANCE_CONFIDENCE_THRESHOLD": 0.70,
    "EMOTION_ASSISTANCE_ROLLOUT_PERCENT": 0,  # active mode deterministic 0/5/25/50/100 rollout
    "EMOTION_EVENT_VOICE": True,       # 語音模式開始／結束皆在背景觸發分析
    "EMOTION_INCLUDE_STT": True,        # 語音結束分析同時提供 STT 逐字稿與影音
    "EMOTION_ANALYSIS_MODE": "media_plus_stt",  # media_only | media_plus_stt | paired
    "EMOTION_PROMPT": _prompts.EMOTION_PROMPT,
    "EMOTION_PROMPT_MAX_CHARS": 800,
    # ── 互動障礙偵測閾值 ──────────────────────
    "BARRIER_DWELL_TIMEOUT_SEC": 40,        # 選單頁停留超過此秒數視為 menu_hesitation
    "BARRIER_CATEGORY_SWITCH_MAX": 4,       # 分類切換次數達此值視為 menu_hesitation
    "BARRIER_CART_REMOVE_MAX": 2,           # 購物車移除次數達此值視為 menu_hesitation
    "BARRIER_PAYMENT_FAIL_MAX": 1,          # 付款失敗次數達此值視為 payment_confusion
    # ── 機台識別 ─────────────────────────────────────────────────
    "KIOSK_NAME": "機台01",
    # ── Object storage (binary outside PostgreSQL; metadata may be durable) ──
    "OBJECT_STORAGE_BACKEND": os.getenv("OBJECT_STORAGE_BACKEND", "memory"),  # memory|local|s3
    "OBJECT_STORAGE_LOCAL_ROOT": os.getenv("OBJECT_STORAGE_LOCAL_ROOT", ""),
    "OBJECT_STORAGE_SIGNING_SECRET": os.getenv("OBJECT_STORAGE_SIGNING_SECRET", ""),
    "OBJECT_STORAGE_ENCRYPTION": os.getenv("OBJECT_STORAGE_ENCRYPTION", "none-test"),
    "OBJECT_STORAGE_ENCRYPTION_KEY": os.getenv("OBJECT_STORAGE_ENCRYPTION_KEY", ""),
    "OBJECT_STORAGE_ENCRYPTION_KEY_VERSION": os.getenv("OBJECT_STORAGE_ENCRYPTION_KEY_VERSION", "v1"),
    "OBJECT_STORAGE_ENDPOINT": os.getenv("OBJECT_STORAGE_ENDPOINT", ""),
    "OBJECT_STORAGE_BUCKET": os.getenv("OBJECT_STORAGE_BUCKET", ""),
    "OBJECT_STORAGE_ACCESS_KEY": os.getenv("OBJECT_STORAGE_ACCESS_KEY", ""),
    "OBJECT_STORAGE_SECRET_KEY": os.getenv("OBJECT_STORAGE_SECRET_KEY", ""),
    "OBJECT_STORAGE_REGION": os.getenv("OBJECT_STORAGE_REGION", "auto"),
    "OBJECT_STORAGE_S3_ENCRYPTION": os.getenv("OBJECT_STORAGE_S3_ENCRYPTION", "provider-managed"),
}

PUBLIC_SETTINGS_KEYS = {
    "DEMO_PUBLIC_MODE",
    "EMOTION_ENABLED",
    "EMOTION_CLIP_SEC",
    "EMOTION_EVENT_VOICE",        # Kiosk 需要：控制語音模式開始／結束的背景分析
    "EMOTION_INCLUDE_STT",         # Kiosk 需要：STT 完成後啟動影音＋逐字稿分析
    "EMOTION_ANALYSIS_MODE",
    "AI_PUSH_REFRESH_SEC",
    # Kiosk 決定「換一個」行為時需要，故列為公開投影。
    "AI_PUSH_EXCLUDE_SEEN",
    "AI_PUSH_PREFETCH",
    "PASSIVE_VOICE_KEYWORDS",
    "MEMBER_ENABLED",
    "MEMBER_USUALS_COUNT",
}


LLM_ROUTING_POLICIES = ("local_first", "cloud_first", "local_only", "cloud_only")
# Cloud provider choices this settings document has carried over time. NVIDIA NIM is now the
# only cloud text provider the runtime supports; a stored choice of any of these just means
# "this store previously preferred the cloud half of the chain" and maps to cloud_first.
_LEGACY_CLOUD_PROVIDER_NAMES = ("gemini", "openai")

# NIM Model Catalog: the curated, developer-maintained set of NVIDIA NIM model IDs offered in
# the Admin dropdown for NIM_MODEL_NAME. Admin may additionally save Custom NIM Model Entries
# (NIM_CUSTOM_TEXT_MODELS) that are appended to this list without validation against NVIDIA's
# actual catalog.
NIM_TEXT_MODEL_CATALOG = (
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.3-70b-instruct",
    "mistralai/mistral-7b-instruct-v0.3",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "deepseek-ai/deepseek-v4-flash",
)
# Voice keeps a separate, smaller/faster catalog for NIM_VOICE_MODEL — same mechanism
# (curated list + admin-added Custom NIM Model Entries via NIM_CUSTOM_VOICE_MODELS).
NIM_VOICE_MODEL_CATALOG = (
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.2-3b-instruct",
    "meta/llama-3.2-1b-instruct",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
)


def migrate_llm_routing_settings(settings: dict) -> dict:
    """Derive the routing policy from legacy provider-selection keys.

    Earlier versions let a store name which cloud provider it wanted (`AI_PROVIDER`, then
    `LLM_CLOUD_PROVIDER` choosing between Gemini and an OpenAI-compatible endpoint). The
    runtime now has exactly one cloud provider, NVIDIA NIM, so there is nothing left to
    choose — only whether the store prefers cloud or local stays a real decision. A stored
    cloud preference becomes cloud_first so an offline store still gets served; the legacy
    keys are dropped so there is one source of truth.
    """

    result = dict(settings or {})
    legacy = str(result.pop("AI_PROVIDER", "") or "").strip().lower()
    legacy_cloud_provider = str(result.pop("LLM_CLOUD_PROVIDER", "") or "").strip().lower()
    result.pop("QA_AI_PROVIDER", None)
    result.pop("ENABLE_GEMINI_OPTIONS", None)
    prefers_cloud = legacy in _LEGACY_CLOUD_PROVIDER_NAMES or legacy_cloud_provider in _LEGACY_CLOUD_PROVIDER_NAMES
    if str(result.get("LLM_ROUTING_POLICY") or "").strip().lower() not in LLM_ROUTING_POLICIES:
        result["LLM_ROUTING_POLICY"] = "cloud_first" if prefers_cloud else "local_first"
    for key in CREDENTIAL_SETTING_KEYS:
        result.pop(key, None)
    return result


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


def _apply_security_env_overrides(settings: dict) -> None:
    settings["APP_ENV"] = APP_ENV
    settings["SECURITY_ENFORCED"] = is_security_enforced()

    for env_key in (
        "MAX_UPLOAD_BYTES",
        "RATE_LIMIT_DEFAULT_PER_MINUTE",
    ):
        env_value = os.getenv(env_key)
        if env_value in (None, ""):
            continue
        if env_key in ("MAX_UPLOAD_BYTES", "RATE_LIMIT_DEFAULT_PER_MINUTE"):
            try:
                settings[env_key] = int(env_value)
            except ValueError:
                continue
        else:
            settings[env_key] = env_value

    for env_key in (
        "SECURITY_ENFORCED",
        "RATE_LIMIT_ENABLED",
        "ENABLE_DEBUG_ROUTES",
        "ENABLE_DEMO_ROUTES",
        "ENABLE_DIAGNOSTIC_ROUTES",
    ):
        env_value = str(os.getenv(env_key, "")).lower()
        if env_value in ("1", "true", "yes", "on"):
            settings[env_key] = True
        elif env_value in ("0", "false", "no", "off"):
            settings[env_key] = False

    settings["SECURITY_ENFORCED"] = is_security_enforced()

    if is_production() and not ALLOW_UNSAFE_PRODUCTION_ROUTES:
        settings["ENABLE_DEBUG_ROUTES"] = False
        settings["ENABLE_DEMO_ROUTES"] = False
        settings["ENABLE_DIAGNOSTIC_ROUTES"] = False

def _finalize_settings(settings: dict) -> dict:
    """Apply env-derived overrides shared by every settings source (JSON file or Postgres)."""

    settings = migrate_llm_routing_settings(settings)

    if str(os.getenv("DEMO_PUBLIC_MODE", "")).lower() in ("1", "true", "yes", "on"):
        settings["DEMO_PUBLIC_MODE"] = True

    for env_key in ("DATABASE_BACKEND", "DATABASE_TOPOLOGY", "DATABASE_URL", "MEMBER_SESSION_TTL_SEC"):
        env_value = os.getenv(env_key)
        if env_value not in (None, ""):
            if env_key == "MEMBER_SESSION_TTL_SEC":
                try:
                    settings[env_key] = int(env_value)
                except ValueError:
                    pass
            else:
                settings[env_key] = env_value
    dual_write_env = str(os.getenv("ENABLE_MEMBER_DUAL_WRITE", "")).lower()
    if dual_write_env in ("1", "true", "yes", "on"):
        settings["ENABLE_MEMBER_DUAL_WRITE"] = True
    elif dual_write_env in ("0", "false", "no", "off"):
        settings["ENABLE_MEMBER_DUAL_WRITE"] = False
    _apply_security_env_overrides(settings)
    return settings


def _use_postgres_settings() -> bool:
    from repositories import postgres_utils

    return postgres_utils.use_postgres()


_pg_settings_cache = None
_pg_settings_last_check = 0.0


def _load_settings_postgres():
    """Postgres is authoritative once selected — never fall back to the JSON file, per
    postgres_utils's "never split authority" rule. TTL-cached like the JSON path's mtime
    check so 215+ config.get() call sites don't turn into a database round-trip each."""

    global _pg_settings_cache, _pg_settings_last_check

    now = time.time()
    if _pg_settings_cache is not None and now - _pg_settings_last_check < 1.0:
        return _pg_settings_cache.copy()

    with _settings_lock:
        now = time.time()
        if _pg_settings_cache is not None and now - _pg_settings_last_check < 1.0:
            return _pg_settings_cache.copy()

        from repositories import commercial_settings_repository

        settings = _deep_merge(DEFAULT_SETTINGS.copy(), commercial_settings_repository.get_settings())
        settings = _finalize_settings(settings)

        _pg_settings_cache = settings.copy()
        _pg_settings_last_check = now
        return settings.copy()


def load_settings():
    global _settings_cache, _settings_mtime, _settings_last_check

    if _use_postgres_settings():
        return _load_settings_postgres()

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

        settings = _finalize_settings(settings)

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


def public_settings(settings: dict | None = None) -> dict:
    """Project a settings document down to the keys a customer-facing client may receive."""

    source = settings if isinstance(settings, dict) else load_settings()
    return {key: source.get(key, DEFAULT_SETTINGS.get(key)) for key in PUBLIC_SETTINGS_KEYS}


def load_public_settings():
    return public_settings()


def with_effective_emotion_prompt(settings: dict | None) -> dict:
    """Expose the prompt actually used at runtime in the Admin editor."""
    effective = dict(settings or {})
    if not str(effective.get("EMOTION_PROMPT") or "").strip():
        effective["EMOTION_PROMPT"] = DEFAULT_SETTINGS["EMOTION_PROMPT"]
    return effective

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
    runtime_values = {
        "APP_ENV": APP_ENV,
        "SECURITY_ENFORCED": is_security_enforced(),
        "KIOSK_DEVICE_TOKEN": KIOSK_DEVICE_TOKEN,
        "ALLOW_POSTGRES_JSON_FALLBACK": ALLOW_POSTGRES_JSON_FALLBACK,
        "ENABLE_LEGACY_KIOSK_TOKEN": ENABLE_LEGACY_KIOSK_TOKEN,
        "ADMIN_SESSION_COOKIE_NAME": ADMIN_SESSION_COOKIE_NAME,
        "ADMIN_SESSION_TTL_SEC": ADMIN_SESSION_TTL_SEC,
        "ADMIN_MANAGER_IDLE_TIMEOUT_SEC": ADMIN_MANAGER_IDLE_TIMEOUT_SEC,
        "DEVICE_SESSION_COOKIE_NAME": DEVICE_SESSION_COOKIE_NAME,
        "DEVICE_SESSION_TTL_SEC": DEVICE_SESSION_TTL_SEC,
        "DEVICE_CREDENTIAL_TTL_DAYS": DEVICE_CREDENTIAL_TTL_DAYS,
        "DEVICE_CREDENTIAL_ROTATION_GRACE_SEC": DEVICE_CREDENTIAL_ROTATION_GRACE_SEC,
        "DEFAULT_TENANT_ID": DEFAULT_TENANT_ID,
        "DEFAULT_STORE_ID": DEFAULT_STORE_ID,
        "DEFAULT_DEVICE_ID": DEFAULT_DEVICE_ID,
        "REDIS_URL": REDIS_URL,
        "SHARED_RATE_LIMIT_ENABLED": SHARED_RATE_LIMIT_ENABLED,
    }
    emotion_enabled_env = str(os.getenv("EMOTION_ENABLED", "")).strip().lower()
    if emotion_enabled_env in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        # Emotion enablement is process-local. A startup script must not be
        # overridden by a stale value persisted in shared UI settings.
        runtime_values["EMOTION_ENABLED"] = emotion_enabled_env in {"1", "true", "yes", "on"}
    if key in runtime_values:
        return runtime_values[key] if runtime_values[key] not in (None, "") else default
    value = load_settings().get(key)
    if value is not None and value != "":
        return value
    return DEFAULT_SETTINGS.get(key, default)
