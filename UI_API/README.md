# UI_API — 智慧自助點餐系統

FastAPI 後端 + POS kiosk 前端 + 後台管理介面。

---

## 啟動

```bash
cd UI_API && conda activate emotion_ui
python main.py
```

| 入口 | 說明 |
|------|------|
| `http://127.0.0.1:8000` | POS kiosk 客戶端 |
| `http://127.0.0.1:8001` | 後台管理 |

port 8000 永遠是 POS、8001 永遠是後台，兩者完全隔離。

---

## 系統架構

```
UI_API/
├── main.py               ← 唯一入口，sys.path 橋接 backend/
├── config.py             ← 靜態設定（.env）+ 動態設定（settings.json）
├── backend/              ← Python 後端
│   ├── ai_services.py
│   ├── database.py
│   ├── routes/
│   ├── services/
│   ├── repositories/
│   ├── realtime/
│   ├── utils/
│   ├── prompts/
│   └── menu_data/
├── frontend/             ← 前端資源（FastAPI 掛載為 /static/）
│   ├── pos/              ← POS kiosk
│   ├── admin/            ← 後台
│   └── shared/           ← 共用模組
├── learning_data/        ← Runtime JSON 資料（不提交 git）
└── menu_data/            ← 菜單（config.py 路徑依賴，保持根目錄）
```

---

## API 完整清單

### 前台（POS）

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/` | POS kiosk 首頁 |
| `GET` | `/pos` | POS kiosk（同上） |
| `GET` | `/api/public_settings` | 公開設定（前端啟動用） |
| `GET` | `/api/menu` | 菜單清單 |
| `POST` | `/api/ask` | 語音點餐：音訊 → STT → LLM → TTS |
| `POST` | `/api/ai_push` | AI 推播：從菜單選 1 品推薦 |
| `POST` | `/api/emotion/analyze` | Emotion-LLaMA 通用入口（向下相容） |
| `POST` | `/api/emotion/analyze_event` | 事件驅動分析：截片 → Gradio → log |
| `GET` | `/api/emotion/intervention_logs` | 取得 Emotion-LLaMA 介入紀錄 |
| `DELETE` | `/api/emotion/intervention_logs` | 清空 Emotion-LLaMA 介入紀錄 |
| `POST` | `/api/interaction_event` | 保存 POS 操作事件 |
| `POST` | `/api/barrier_state` | 推論互動障礙狀態 + 產生介入 |
| `POST` | `/api/intervention_result` | 回寫介入結果（閉環） |
| `POST` | `/api/checkout` | 結帳：保存 session log |
| `GET` | `/api/session_stats` | 推播點擊統計 |
| `WS` | `/ws/pos/{session_id}` | POS WebSocket |

### 後台（Admin）

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/admin` | 後台管理首頁 |
| `GET` | `/api/settings` | 讀取設定（需 admin token） |
| `POST` | `/api/settings` | 儲存設定 |
| `POST` | `/api/menu` | 更新菜單 |
| `GET` | `/api/logs` | Session logs 清單 |
| `DELETE` | `/api/logs` | 清空 session logs |
| `DELETE` | `/api/logs/{index}` | 刪除單筆 log |
| `DELETE` | `/api/session_stats` | 清空統計 |
| `GET` | `/api/intervention_stats` | 介入統計（成功率、障礙分布） |
| `DELETE` | `/api/intervention_logs` | 清空介入紀錄 |
| `DELETE` | `/api/interaction_events` | 清空互動事件 |
| `WS` | `/ws/admin/global` | Admin WebSocket（staff_notify、settings_changed） |

### Demo / Debug

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/api/demo/trigger_scenario` | 觸發測試情境（PoC 驗證用） |
| `GET` | `/api/debug/intervention_logs/{session_id}` | 查詢介入紀錄（需 ENABLE_DEBUG_ROUTES=true） |

---

## 前端架構

### `frontend/pos/` — POS kiosk

| 檔案 | 職責 |
|------|------|
| `index.html` | 16:9 kiosk UI 骨架 |
| `app.js` | 主控制器：菜單渲染、購物車、語音、AI 推播、猶豫彈窗、互動追蹤、Emotion 事件觸發 |
| `cart.js` | 購物車 factory（createCartManager） |
| `media.js` | 媒體裝置管理 + rolling buffer（`startRollingBuffer`, `capturePreEventClip`, `stopRollingBuffer`） |

### `frontend/admin/` — 後台

| 檔案 | 職責 |
|------|------|
| `admin.html` | 後台管理頁面骨架 |
| `admin.js` | 統計圖表、Session 紀錄表格、TOP3 品項 |

### `frontend/shared/` — 共用

| 檔案 | 職責 |
|------|------|
| `api.js` | 所有後端 API 呼叫封裝 |
| `ui.js` | 共用 UI 元件（通知、切換等）|
| `realtime_client.js` | WebSocket 連線管理 |
| `styles.css` | 全域樣式 |

---

## 後端架構

### `backend/routes/` — HTTP Endpoints

| 檔案 | 路由前綴 | 主要功能 |
|------|----------|----------|
| `core_routes.py` | `/`, `/api` | 首頁、設定、checkout、logs |
| `menu_routes.py` | `/api` | 菜單讀寫 |
| `voice_routes.py` | `/api` | 語音點餐（POST /api/ask） |
| `ai_push_routes.py` | `/api` | AI 推播（POST /api/ai_push） |
| `emotion_routes.py` | `/api/emotion` | Emotion-LLaMA 分析、事件驅動、介入紀錄 |
| `interaction_routes.py` | `/api` | POS 事件、障礙狀態、介入統計 |
| `realtime_routes.py` | `/ws` | WebSocket |
| `demo_routes.py` | `/api/demo` | 測試情境觸發 |
| `debug_routes.py` | `/api/debug` | Debug 查詢（ENABLE_DEBUG_ROUTES） |

### `backend/services/` — 業務邏輯

| 檔案 | 職責 |
|------|------|
| `voice_service.py` | 語音流程：STT → Ollama → TTS |
| `ai_push_service.py` | 推播邏輯：Ollama 選品 + 促購短句 |
| `emotion_service.py` | Emotion-LLaMA 事件分析：`analyze_event()`、語音快取（`get/clear_voice_emotion_cache()`） |
| `barrier_state_service.py` | POS 事件 + 語音 → barrier_state 推論 |
| `intervention_service.py` | barrier_state → intervention_action 決策 |
| `intervention_pipeline_service.py` | 完整介入流程：事件→障礙→介入→log→推播 |
| `interaction_event_service.py` | POS 事件標準化 |
| `scenario_service.py` | 情境 ID / label 對照表與正規化 |
| `recommendation_service.py` | 語音點餐白名單校正、模糊比對、數量解析 |

### `backend/repositories/` — 資料存取

| 檔案 | 儲存位置 | 職責 |
|------|----------|------|
| `menu_repository.py` | `menu_data/menu.json` | 菜單讀寫（含 mtime 快取） |
| `log_repository.py` | `learning_data/session_logs.json` | Session log 讀寫 |
| `session_repository.py` | 記憶體 dict | Session 狀態（語音對話歷史） |
| `interaction_event_repository.py` | `learning_data/interaction_events.json` | 事件與介入紀錄 |
| `emotion_log_repository.py` | `learning_data/emotion_intervention_logs.json` | Emotion-LLaMA 分析紀錄 |

### `backend/realtime/`

| 檔案 | 職責 |
|------|------|
| `connection_manager.py` | WebSocket 連線 pool 管理 |
| `event_bus.py` | 統一推播介面（publish_intervention、publish_to_admin） |

### `backend/utils/`

| 檔案 | 職責 |
|------|------|
| `text_utils.py` | 繁簡轉換、CJK 偵測、情緒標籤正規化 |
| `file_utils.py` | 二進位檔寫入 |
| `auth_utils.py` | Admin token 驗證 |

---

## 設定參考

設定分兩層：

**靜態（`.env`，需重啟）**
```
OLLAMA_API_URL, GEMINI_API_KEY, APP_HOST, APP_PORT, ADMIN_PORT
NGROK_AUTHTOKEN, POS_DEMO_TOKEN, ADMIN_DEMO_TOKEN
```

**動態（`learning_data/settings.json`，後台即時修改）**

主要設定：

| 設定 Key | 預設 | 說明 |
|----------|------|------|
| `MODEL_NAME` | `qwen3.5:4b` | Ollama 主要模型（AI 推播） |
| `VOICE_ASSIST_MODEL` | `qwen3.5:4b` | 語音協助模型 |
| `VOICE_ASSIST_SYSTEM_PROMPT` | `""` | 語音 LLM 系統 prompt（空 = 使用內建預設） |
| `STT_PROVIDER` | `faster_whisper` | STT 來源：`faster_whisper` / `openai_compatible` |
| `STT_MODEL` | `small` | faster-whisper 模型大小（tiny/small/medium） |
| `TTS_PROVIDER` | `melo` | TTS 來源：`melo` / `edge` / `openai_compatible` |
| `EDGE_TTS_VOICE` | `zh-TW-HsiaoChenNeural` | Edge TTS 中文語音 |
| `EDGE_TTS_VOICE_EN` | `en-US-JennyNeural` | Edge TTS 英文語音 |
| `TTS_SPEED` | `1.0` | MeloTTS 語速 |
| `RAG_ENABLED` | `true` | RAG 開關（無文件時自動跳過） |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | fastembed 嵌入模型 |
| `EMOTION_LLAMA_ENABLED` | `false` | Emotion-LLaMA 事件分析開關 |
| `EMOTION_LLAMA_CLIP_SEC` | `2.0` | 截片秒數 |
| `EMOTION_LLAMA_QUALITY_CHECK` | `true` | 品質快篩 |
| `EMOTION_LLAMA_AFFECT_VOICE` | `false` | 情緒結果注入語音 prompt |
| `EMOTION_LLAMA_AFFECT_BARRIER` | `false` | 情緒結果觸發 barrier pipeline |
| `ENABLE_DEBUG_ROUTES` | `false` | Debug API 開關 |
| `ENABLE_GEMINI_OPTIONS` | `false` | Gemini API 開關 |

---

## Runtime 資料（`learning_data/`）

| 檔案 | 說明 |
|------|------|
| `settings.json` | 後台動態設定 |
| `session_logs.json` | 結帳 session 紀錄（含 ai_push_cart_count、cart_sources） |
| `interaction_events.json` | POS 操作事件序列 |
| `intervention_logs.json` | 介入紀錄與結果 |
| `emotion_intervention_logs.json` | Emotion-LLaMA 事件分析紀錄 |

---

## 菜單格式

`menu_data/menu.json` 格式：

```json
[
  {
    "id": "MCD001",
    "name": "大麥克",
    "category": "超值全餐",
    "price": 105,
    "description": "兩片牛肉...",
    "image": "https://...",
    "aliases": ["大mac", "bigmac"]
  }
]
```

ID 格式固定 `MCDxxx`，前後端、LLM 白名單校正均依賴此格式。

---

## 開發檢查

```bash
# Python 語法
python3 -m py_compile main.py config.py backend/ai_services.py
python3 -m py_compile backend/routes/core_routes.py backend/services/voice_service.py

# JS 語法
node --check frontend/pos/app.js
node --check frontend/shared/api.js

# 服務確認
curl http://127.0.0.1:8000/api/public_settings
curl http://127.0.0.1:8001/api/settings
```
