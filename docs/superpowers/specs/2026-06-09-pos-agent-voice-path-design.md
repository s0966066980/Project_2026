# pos_agent Stage 2 — 語音路徑（Voice Path）設計規格

- **日期**：2026-06-09
- **目標目錄**：`/home/oliver/pos_agent`（在第一階段 agent 核心之上擴充）
- **狀態**：設計已核准，待寫實作計畫
- **前置**：Stage 1（agent 核心 + 最小 API）已完成，51 測試通過

---

## 1. 目標與範圍

在既有 agent 核心之上加上**語音點餐路徑**：`音訊 → STT → orchestrator.handle → TTS`，重用 agent 核心（不重寫 LLM 邏輯）。

### 本 spec 範圍（已核准決策）

- **STT/TTS provider**：各一個實作（`faster_whisper` STT + `edge` TTS），但保留 ABC + factory 抽象，日後可加。
- **非串流**：只做 `POST /api/ask`（完整 STT → agent → 完整 TTS），串流延後。
- **Session 持久化**：新增 `domain/session.py`（JSON 存），並讓 `Agent` 注入對話歷史，支援多輪點餐（「加一杯可樂」→「改成兩杯」）。文字 `/api/chat` 一併獲得 session 記憶。
- **多語言**：保留 STT 自動偵測 zh/en → 選對應 TTS 聲音 + 回覆語言。

### 不變原則（沿用）

- 菜單白名單在 tool handler 內強制，LLM 不可幻覺餐點。
- 讀設定統一 `config.get("KEY")`。
- 分層：`api/` 薄、`agents/`+`tools/` 邏輯、`domain/` 資料存取。
- 語音失敗應**優雅降級**（TTS 壞掉仍回文字，不擋訂單）。

### 延後（非本 spec）

串流 `/api/ask/stream`、MeloTTS / OpenAI-compatible STT/TTS provider、心情星星 context 注入。

---

## 2. 新增結構

```
app/
├── voice/
│   ├── stt.py        STTProvider(ABC) + FasterWhisperSTT + get_stt()
│   ├── tts.py        TTSProvider(ABC) + EdgeTTSProvider + get_tts()
│   ├── fakes.py      FakeSTT / FakeTTS（確定性測試用）
│   └── pipeline.py   handle_voice()：STT → agent → 持久化 → TTS
├── domain/session.py JSON session 存（history + cart）
└── api/voice_routes.py  POST /api/ask
```

`voice/` 為新 package（`__init__.py`），把語音相關檔案聚在一起（會一起變動的放一起）。

---

## 3. STT / TTS Provider 抽象

沿用 Project_2026 的 ABC + factory 模式，與 LLM provider 哲學一致。

### `voice/stt.py`
```python
class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str) -> dict: ...
        # → {"text": str, "language": "zh"|"en"}

class FasterWhisperSTT(STTProvider):
    # 延遲 import faster_whisper / torch；類別層級快取模型；
    # GPU 失敗退回 CPU int8；vad_filter 開；language=config STT_LANGUAGE(可 None 自動偵測)
    # 回傳 language 正規化為 "zh" / "en"

def get_stt() -> STTProvider:
    # config STT_PROVIDER（預設 "faster_whisper"）；未來可加 openai_compatible
```

### `voice/tts.py`
```python
class TTSProvider(ABC):
    audio_format: str = "wav"
    @abstractmethod
    async def synthesize(self, text: str, lang: str = "zh") -> bytes: ...
    async def synthesize_base64(self, text: str, lang: str = "zh") -> str:
        # 空字串 → 回 ""；否則 synthesize 後 base64

class EdgeTTSProvider(TTSProvider):
    audio_format = "mp3"
    # 延遲 import edge_tts；voice 依 lang 選（zh-TW-HsiaoChenNeural / en-US-JennyNeural，可由 config 覆寫）

def get_tts() -> TTSProvider:
    # config TTS_PROVIDER（預設 "edge"）
```

**SDK 延遲 import**：`faster_whisper`/`torch`/`edge_tts` 都在方法/`_init` 內 import，模組可在未安裝時被匯入（測試/CI 不需安裝）。

### `voice/fakes.py`（測試用）
```python
class FakeSTT(STTProvider):
    def __init__(self, text="我要大麥克", language="zh"): ...
    async def transcribe(self, audio_path): return {"text": self.text, "language": self.language}

class FakeTTS(TTSProvider):
    audio_format = "mp3"
    async def synthesize(self, text, lang="zh"): return b"FAKE_AUDIO"
```

---

## 4. Session 持久化（`domain/session.py`）

JSON 檔存於 `data/sessions/<session_id>.json`。屬 domain 層（只做資料存取，無業務邏輯）。

```python
# turn 結構：{"user": str, "ai": str, "cart_actions": list, "lang": str, "ts": iso8601}

def get_history(session_id: str) -> list:
    # 回最近 N 輪（config VOICE_HISTORY_MAX_TURNS，預設 4）；檔不存在回 []

def append_turn(session_id, user, ai, cart_actions, lang) -> None:
    # 讀現有 → append → 寫回（建立 data/sessions/ 目錄）
```

- session 目錄路徑：`config.get("SESSION_DIR")`（預設 `data/sessions`，已在 `.gitignore`）。
- session_id 做檔名前需基本清洗（只允許英數/底線/連字號，避免路徑穿越）。

---

## 5. Agent 歷史 + 語言注入（`agents/base.py` 擴充）

### `AgentContext`（`context.py`）新增欄位
```python
lang: str = "zh"     # 既有：session_id, cart, history, mood, cart_actions, trace
```

### `Agent.run` 行為擴充
- 若 `ctx.history` 非空 → 用 `_format_history(ctx.history)` 組出 `【對話歷史】\n顧客：…\n系統：…` 區塊，**前置到當前 user 訊息**（provider-agnostic）。
- 若 `ctx.lang == "en"` → 在 system prompt 後追加一行語言指示（如 `Reply to the customer in English.`）。
- 既有 tool-calling 迴圈、白名單、max_iters 不變。

```python
def _format_history(history: list, max_turns: int) -> str:
    # 取最近 max_turns 輪 → "【對話歷史（最近幾輪）】\n顧客：..\n系統：.." or ""
```

**設計決策**：歷史以**文字區塊**注入 user 訊息（沿用 Project_2026），不重播為多個 Message turn——較簡單、provider 無關、易測。

### orchestrator / chat 一併受惠
- `orchestrator.handle(user_input, ctx, provider=None)` 已吃 ctx；ctx 帶 history/lang 即生效。
- `route()` 仍只看當前輸入（後續句如「改成兩杯」會落入預設 ordering，安全）。
- `api/chat_routes.py` 改為：載入 session history → 建 ctx → handle → 寫回 turn（與語音共用同一 session 對話）。

---

## 6. 語音 pipeline（`voice/pipeline.py`）

```python
async def handle_voice(session_id: str, audio_path: str, multi_lang: bool = True) -> dict:
    stt = get_stt()
    try:
        r = await stt.transcribe(audio_path)
    except Exception as e:
        return {"status": "error", "message": f"STT 失敗: {e}",
                "user_text": "", "ai_response": "", "cart_actions": [],
                "audio_base64": "", "audio_format": "", "detected_lang": "zh"}
    user_text = (r.get("text") or "").strip()
    lang = (r.get("language", "zh") if multi_lang else "zh")
    if not user_text:
        return {"status": "error", "message": "無法辨識語音內容", ...空欄位..., "detected_lang": lang}

    history = session.get_history(session_id)
    ctx = AgentContext(session_id=session_id, history=history, lang=lang)
    result = await asyncio.to_thread(orchestrator.handle, user_text, ctx)

    await asyncio.to_thread(session.append_turn, session_id, user_text,
                            result.ai_response, result.cart_actions, lang)

    tts = get_tts()
    try:
        audio_b64 = await tts.synthesize_base64(result.ai_response, lang)
        audio_format = tts.audio_format
    except Exception as e:
        print(f"⚠️ TTS 失敗: {e}")
        audio_b64, audio_format = "", ""

    return {"status": "success", "user_text": user_text, "ai_response": result.ai_response,
            "cart_actions": result.cart_actions, "trace": result.trace,
            "audio_base64": audio_b64, "audio_format": audio_format, "detected_lang": lang}
```

- `orchestrator.handle` 為同步（agent loop 同步），用 `asyncio.to_thread` 包進 async pipeline。

---

## 7. 路由（`api/voice_routes.py`）

```python
@router.post("/ask")
async def ask(session_id: str = Form(...), media: UploadFile = File(...),
              multi_lang: str = Form(default="true")):
    # 存 temp 檔 → pipeline.handle_voice → finally 刪 temp 檔
```

- 與其他 route 一樣薄。`main.py` 掛載 voice_router（prefix `/api`）。
- `VOICE_ENABLED` 設定已存在；route 一律註冊（stage 1 已預留旗標，本階段啟用）。

---

## 8. 設定新增（`config.py` DEFAULT_SETTINGS）

```
STT_PROVIDER = "faster_whisper"
STT_MODEL = "small"
STT_LANGUAGE = ""              # 空 = 自動偵測
TTS_PROVIDER = "edge"
EDGE_TTS_VOICE = "zh-TW-HsiaoChenNeural"
EDGE_TTS_VOICE_EN = "en-US-JennyNeural"
VOICE_HISTORY_MAX_TURNS = 4
SESSION_DIR = "<project>/data/sessions"   # 已在 .gitignore
```

---

## 9. 錯誤處理

- STT 例外或空辨識 → 結構化 error dict，不崩潰。
- TTS 例外 → 回文字 + 空 `audio_base64`（語音降級為文字，不擋訂單）。
- 缺 `faster-whisper`/`edge-tts` 套件 → 延遲 import，只在實際用到該 provider 時清楚報錯。
- session 寫入失敗不應中斷回應（記 log、繼續回傳結果）。

---

## 10. 測試策略（全確定性，不需真實模型）

- **FakeSTT / FakeTTS**（`voice/fakes.py`）：腳本化文字/語言、固定 bytes。
- **`domain/session.py`**：tmp 目錄 fixture（仿 `menu_file`）——append→get round-trip、最近 N 輪、檔不存在回 []、session_id 清洗。
- **`agents/base.py`**：用 `FakeProvider.calls` 斷言 ctx.history → user 訊息含「對話歷史」區塊；ctx.lang=="en" → system prompt 含英文指示。
- **`voice/pipeline.py`**：monkeypatch `get_stt`/`get_tts` + `factory.get_provider_with_fallback`；斷言端到端 dict（含 audio_base64 非空）+ session 已寫入 turn；STT 空辨識 → error；TTS 失敗 → 文字仍回、audio 空。
- **`api/voice_routes.py`**：TestClient multipart 上傳（假音訊 bytes）+ fakes；斷言回應 JSON。
- **`api/chat_routes.py`**：新增測試確認多輪 session 記憶（第二次請求的 user 訊息含上一輪歷史）。

---

## 11. 已核准的預設

1. 歷史以**文字區塊**注入 user 訊息，不重播為 Message turn。
2. `/api/chat` 也加 session 記憶，與語音共用同一 session 對話。
3. STT/TTS 各一實作（faster_whisper / edge），保留抽象。
4. 非串流；多語言 zh/en 自動偵測；語言用 runtime 指示而非複製 EN prompt。
