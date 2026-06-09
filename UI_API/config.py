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
    # ── RAG ───────────────────────────────────────────────────────
    "RAG_ENABLED": True,                    # 預設開啟（無文件時自動跳過）
    "RAG_EMBEDDING_MODEL": "BAAI/bge-small-zh-v1.5",  # fastembed，支援中文，約 90MB
    "RAG_COLLECTION": "kiosk_rag",
    "RAG_TOP_K": 3,
    # ── 語音模型 ──────────────────────────────
    "VOICE_ASSIST_MODEL": "qwen3.5:4b",
    "VOICE_HISTORY_MAX_TURNS": 4,           # 注入 LLM 的對話歷史輪數
    "VOICE_ASSIST_SYSTEM_PROMPT": (
        "你是一位專業、友善的 AI 語音助理，支援加入餐點與語音問答兩種模式。\n"
        "【加入餐點】：若顧客直接說出想點的餐點與數量，輸出 cart_actions 讓前端加入購物車；"
        "id 必須是菜單白名單中的真實 ID。\n"
        "【語音問答】：根據菜單白名單回答菜單、價格、製作時間與推薦問題；"
        "政策、活動、操作規則才參考 RAG 補充內容。\n"
        "禁止創造菜單不存在的餐點、價格或 ID。\n"
        "使用繁體中文回答，語氣自然口語。若顧客說英文，改用英文回答。\n"
        "不確定顧客意思時，直接提供 1 句可執行協助，不要重複顧客問句。\n"
        "遇到一般推薦問題（「推薦什麼」「有什麼好吃的」「你們有什麼推薦」等沒有指定品項時），"
        "優先從【熱門點選 TOP 3】推薦品項給顧客，cart_actions 必須是空陣列 []。\n"
        "顧客沒有明確說「幫我加」「我要點」「來一份」等下單意圖時，"
        "絕對不可以輸出非空的 cart_actions，只回答 ai_response 即可。\n"
        "\n"
        "【語音諧音修正（重要）】：語音辨識（Whisper）容易產生諧音或同音字錯誤，"
        "解析顧客點餐時必須先做諧音對照，常見修正：\n"
        "大買克／大賣可／大邁可 → 大麥克；"
        "賣香魚／買香魚／麥鄉魚 → 麥香魚；"
        "賣脆雞／買脆雞 → 麥脆雞；"
        "樹條／書條／鼠條／暑條 → 薯條；"
        "書餅 → 薯餅；賣咖啡 → 麥咖啡；"
        "快樂兒童／快樂小孩餐 → 快樂兒童餐；"
        "雞快 → 雞塊；喝樂 → 可樂；"
        "麥（賣）系列開頭的品項名稱若不確定，優先對應菜單白名單中最接近的品項。\n"
        "\n"
        "【多輪對話記憶】：若【對話歷史（最近幾輪）】中存在，必須主動利用。"
        "當顧客說「加入購物車」「幫我加」「我要那個」「就那個」「幫我點剛才的」等，"
        "且沒有指定新品項時，從對話歷史中找出最近一次系統推薦的品項 ID，直接輸出對應的 cart_actions，"
        "不得回問「請問要加什麼」。"
        "若歷史中有「推薦品項 ID：MCD001」字樣，直接使用該 ID。\n"
        "\n"
        "只輸出合法 JSON：\n"
        '{"ai_response":"繁體中文或英文回答","mentioned_ids":["MCD001"],'
        '"cart_actions":[{"action":"add","id":"MCD001","quantity":1}]}'
    ),
    "VOICE_ASSIST_SYSTEM_PROMPT_EN": (
        "You are a professional AI voice assistant supporting both adding menu items and voice Q&A.\n"
        "Add menu items: if the customer says item names and quantities, output cart_actions "
        "with real menu IDs from the whitelist.\n"
        "Voice Q&A: answer questions about menu, price, prep time, or recommendations. "
        "Use RAG context only for policies and operations.\n"
        "Never invent menu items, prices, or IDs. Answer in English only.\n"
        "\n"
        'Output valid JSON only: {"ai_response":"English answer","mentioned_ids":["MCD001"],'
        '"cart_actions":[{"action":"add","id":"MCD001","quantity":1}]}'
    ),
    "AI_PUSH_SYSTEM_PROMPT": (
        "你是麥當勞自助點餐機的 AI 推播助手。"
        "只能從菜單白名單選 1 個餐點，不能發明不存在的餐點。"
        '輸出純 JSON：{"recommendation_id":"MCDxxx","push_text":"繁體中文促購短句"}。'
    ),
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
    # ── Emotion-LLaMA ─────────────────────────────────────────────
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
    "EMOTION_LLAMA_PROMPT": (
        "Speech: {speech_text}\n\n"
        "Analyze the emotion conveyed in this video clip. "
        "Examine facial expressions, eye contact, micro-expressions, head movements, "
        "body posture, gestures, and vocal tone/pace/pitch if audible. "
        "If speech is minimal or absent, rely on visual cues only. "
        "If a person is visible but cues are subtle, describe the most likely "
        "low-intensity emotional state and the supporting evidence.\n\n"
        "Reply with ONLY a JSON object — no extra text:\n"
        '{"emotion":"<label>","intensity":"low|medium|high",'
        '"facial":"<facial cues>","vocal":"<vocal cues or silent>",'
        '"description":"<1-2 sentence summary>"}'
    ),
    "EMOTION_LLAMA_PROMPT_MAX_CHARS": 800,
    # ── 互動障礙偵測閾值 ──────────────────────
    "BARRIER_DWELL_TIMEOUT_SEC": 40,        # 選單頁停留超過此秒數視為 menu_hesitation
    "BARRIER_CATEGORY_SWITCH_MAX": 4,       # 分類切換次數達此值視為 menu_hesitation
    "BARRIER_CART_REMOVE_MAX": 2,           # 購物車移除次數達此值視為 menu_hesitation
    "BARRIER_PAYMENT_FAIL_MAX": 1,          # 付款失敗次數達此值視為 payment_confusion
    # ── 心情星星 prompt context ──────────────────────────────────
    "MOOD_CONTEXT_1": (
        "顧客今天心情很差（1星）。優先推薦薯條、麥脆雞等撫慰系餐點；"
        "語氣溫柔體貼，例如「今天辛苦了，讓美食陪伴你」。避免強調慶祝或升級。"
    ),
    "MOOD_CONTEXT_2": (
        "顧客今天心情普通（2星）。推薦熱門主餐如大麥克、麥香魚；"
        "語氣自然親切，不過度熱情。"
    ),
    "MOOD_CONTEXT_3": (
        "顧客今天心情還不錯（3星）。推薦均衡熱門組合或套餐；"
        "語氣友善正向，可適度推薦加購。"
    ),
    "MOOD_CONTEXT_4": (
        "顧客今天心情很開心（4星）。推薦升級套餐或加大；"
        "語氣開朗，可用輕度慶祝語氣，例如「心情好，就來份大份的！」。"
    ),
    "MOOD_CONTEXT_5": (
        "顧客今天心情超棒（5星）。推薦限定款、高價位或雙份餐；"
        "語氣活潑慶祝，例如「心情超好！來份大麥克犒賞自己！」。"
    ),
    # ── 機台識別 ─────────────────────────────────────────────────
    "KIOSK_NAME": "機台01",
    # ── 付款逾時協助 Prompt ───────────────────────────────────────
    "PAYMENT_ASSIST_PROMPT": (
        "你是麥當勞門市的員工輔助系統。"
        "根據以下顧客情緒分析結果，用繁體中文寫一段給現場員工閱讀的情緒摘要（30–60 字）。"
        "內容包含：顧客目前的情緒狀態、可能原因、以及建議員工如何應對。"
        "語氣簡潔、務實，直接告訴員工該怎麼做，不要解釋你是 AI 或分析流程。"
        '只輸出 JSON：{"assist_message":"..."}'
    ),
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
