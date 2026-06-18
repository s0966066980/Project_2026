# Project_2026 — 智慧自助點餐與客服介入系統

## 專案概述

麥當勞台灣自助點餐 kiosk 原型系統，核心功能：

- **語音點餐**：Whisper STT → Ollama LLM → Edge TTS / MeloTTS
- **AI 推播**：底部推薦欄（`/api/ai_push`）+ 猶豫彈跳視窗
- **協助 Modal**：50 次點擊觸發，提供推薦餐點／語音模式／操作教學三個 panel
- **付款倒數 Modal**：15 秒倒數，逾時觸發 Emotion-LLaMA 分析 + Ollama 協助語
- **互動障礙偵測**：POS 事件 + 語音 → barrier_state → intervention → WebSocket 推送
- **Emotion-LLaMA**：事件觸發截片（rolling buffer）→ Gradio API → 情緒分析 → log
- **RAG**：fastembed 本地向量搜尋，語音點餐 prompt 可選注入（`rag_provider.py`）
- **心情星星**：1–5 顆星 context 注入 AI 推播與語音 prompt
- **後台管理**：設定／統計／Emotion-LLaMA log / RAG 知識庫（port 8001）

---

## Tech Stack

| 層 | 技術 |
|---|---|
| 後端 | Python 3.x、FastAPI（port 8000 + 8001） |
| 前端 | Vanilla JS（ES modules，無框架） |
| LLM | Ollama（qwen3.5:4b）、可選 Gemini API |
| STT | faster-whisper（本地）或 OpenAI-compatible API |
| TTS | Edge TTS（雲端）/ MeloTTS（本地）/ OpenAI-compatible API |
| 視覺 | Emotion-LLaMA（port 7889，可選，事件觸發式） |
| 資料 | JSON 檔（session / log / menu） |
| 設定 | `.env`（靜態）+ `learning_data/settings.json`（後台即時讀寫） |

---

## 專案結構

```
Project_2026/
├── CLAUDE.md
├── UI_API/
│   ├── main.py                        ← 唯一入口，啟動 8000/8001
│   ├── config.py                      ← 靜態設定 + 動態設定管理器（DEFAULT_SETTINGS）
│   ├── backend/
│   │   ├── ai_services.py             ← Ollama / Gemini 文字生成（STT/TTS/視覺走各自 provider）
│   │   ├── database.py                ← 菜單 context、checkout log
│   │   ├── routes/                    ← FastAPI endpoints（詳見下方路由清單）
│   │   ├── services/                  ← 業務邏輯（含 STT/TTS provider 抽象）
│   │   ├── repositories/              ← JSON 資料存取
│   │   ├── realtime/                  ← WebSocket event bus
│   │   ├── utils/                     ← 共用工具
│   │   ├── prompts/defaults.py        ← LLM system prompt 預設值（config.DEFAULT_SETTINGS 引用）
│   │   └── scripts/                   ← 一次性工具腳本
│   ├── frontend/
│   │   ├── pos/                       ← POS kiosk（index.html, app.js, cart.js, media.js）
│   │   ├── admin/                     ← 後台（admin.html, admin.js）
│   │   └── shared/                    ← 共用（api.js, ui.js, styles.css）
│   ├── learning_data/                 ← Runtime 資料（不提交 git）
│   └── menu_data/                     ← 菜單（config.py 路徑依賴）
└── Emotion-LLaMA/
    └── app_EmotionLlamaClient.py      ← 情緒推論服務（port 7889，可選）
```

---

## 啟動方式

```bash
# 主服務（必要）
cd UI_API && conda activate emotion_ui
python main.py
# POS：http://127.0.0.1:8000
# 後台：http://127.0.0.1:8001

# Ollama（必要）
ollama serve && ollama pull qwen3.5:4b

# Emotion-LLaMA（可選）
cd Emotion-LLaMA && conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

---

## 架構規則（修改前必讀）

### 分層職責
- **routes/**：只做請求解析 + 呼叫 service + 回傳 response。**不放業務邏輯。**
- **services/**：業務邏輯主體。不直接讀寫 JSON，透過 repository。
- **repositories/**：JSON 資料存取。**不放業務邏輯、不做 AI 呼叫。**
- **ai_services.py**：Ollama / Gemini 文字生成集中在此，route 層不得直接呼叫。
- **STT / TTS / 視覺**：透過 `services/` 內的 provider 抽象（`stt_service`、`tts_service`、`emotion_service`）呼叫各自後端，不放進 `ai_services.py`。

### 設定系統
- 靜態設定（port、API key）寫在 `.env`，由 `config.py` 讀取。
- 動態設定（AI 參數、功能開關）存在 `learning_data/settings.json`，後台可即時修改。
- **讀設定統一用 `config.get("KEY")`**，不要直接讀 `os.getenv`。
- `PUBLIC_SETTINGS_KEYS`：允許 POS 讀取的 key 集合（Emotion-LLaMA 開關、推播間隔等）。

### 菜單白名單
- 菜單來源：`menu_data/menu.json`（ID 格式：`MCDxxx`）。
- 語音點餐、AI 推播、協助推薦的品項必須通過白名單校正，**不允許 LLM 幻覺餐點**。

### WebSocket
- 統一入口：`/ws/{client_type}/{session_id}`（`client_type`：`pos` / `admin`）
- 事件推送透過 `realtime/event_bus.py`，**不在 route 或 service 直接操作連線**。

### Port 隔離
- `8000`：永遠是 POS 客戶端。`8001`：永遠是後台管理。**不要修改此邏輯。**

---

## 禁止事項

- **不要在 route 直接呼叫 ai_services**，一律透過 service layer。
- **不要在 service 直接讀寫 JSON**，透過 repository。
- **不要在 checkout 加阻擋邏輯**，checkout 應永遠可以完成。
- **不要提交 `.env`、`learning_data/` runtime 資料。**
- **不要修改菜單 ID 格式（MCDxxx）**。
- **innerHTML 插入使用者/LLM 資料前必須用 DOM methods**（防 XSS）。

---

## 核心業務流程

### 語音點餐
```
音訊上傳 → STT（faster-whisper / OpenAI-compatible）
→ 組 prompt（RAG 可選注入 + 心情 context）
→ Ollama LLM → 解析 ai_response + cart_actions
→ TTS（Edge / MeloTTS / OpenAI-compatible）→ 回傳
```

### AI 推播
```
前端定時呼叫 /api/ai_push → ai_push_service.generate()
→ Ollama 從菜單白名單選 1 品 + 促購短句 → 前端底部欄顯示
```

### 協助 Modal（50 次點擊觸發）
```
累積 50 次 pointerdown（isPosActive() 期間）→ showAssistModal()
→ Panel 1：推薦餐點 → /api/assist_recommend（generate_three() × 3）→ 3 張卡片
→ Panel 2：語音模式 → startAskRecording()
→ Panel 3：操作教學 → 點餐步驟說明
```

### 付款倒數 Modal
```
點「在此快速結帳」→ 15 秒倒數
→ 倒數剩 (15 - EMOTION_LLAMA_CLIP_SEC) 秒 → _triggerPaymentEmotionCapture()
  → analyzeEmotionEvent('payment_timeout') → Gradio → Ollama 生成協助語
→ 倒數歸零 → 付款失敗畫面（需要協助嗎？）
→ 點「人員協助付款」→ 顯示 Ollama 協助語 2 秒 → 關閉回付款頁
```

### 互動障礙介入
```
POS 操作事件 → POST /api/interaction_event
→ 語音輸入 / 定時觸發 → POST /api/barrier_state
→ barrier_state_service（事件計數 + 語音判斷 + 情緒提示）
→ intervention_service（決定 action）
→ WebSocket 推送介入卡給 POS → checkout 後回寫 intervention_result
```

### 猶豫彈跳視窗
```
購物車空且無操作 60 秒 → 前端顯示推薦彈窗（choice_hesitation）
→ 顧客點選 → showItemConfirmModal（source: choice_hesitation）
```

---

## barrier_state 與 intervention_action 對照

| barrier_state | intervention_action |
|---|---|
| `normal_operation` | `none` |
| `menu_hesitation` | `recommend_popular_combo` |
| `operation_confusion` | `show_operation_hint` |
| `payment_confusion` | `show_payment_tutorial` |
| `coupon_confusion` | `show_coupon_guide` |
| `impatience_detected` | `call_staff_or_fast_mode` |
| `service_needed` | `call_staff` |
| `potential_complaint` | `call_staff` |
| `low_confidence` | `ask_clarifying_question` |

---

## Emotion-LLaMA 觸發事件

| `event_type` | 觸發時機 | 設定 key |
|---|---|---|
| `tutorial_popup` | 原 operation_hint 彈窗 | `EMOTION_LLAMA_EVENT_TUTORIAL` |
| `payment_timeout` | 付款倒數逾時 | `EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT`（預設開啟） |
| `cancel_guide` | 取消訂單引導彈窗 | `EMOTION_LLAMA_EVENT_CANCEL_GUIDE` |
| `voice_end` | 語音模式結束 | `EMOTION_LLAMA_EVENT_VOICE` |

`payment_timeout` 事件成功後，`emotion_service` 會額外呼叫 Ollama 生成 `assist_response`（協助語），由 `PAYMENT_ASSIST_PROMPT` 設定（後台功能設定可編輯）。

---

## API 路由清單（port 8000 prefix `/api`）

| 路由 | 說明 |
|---|---|
| `POST /api/ask` | 語音點餐（STT + LLM + TTS） |
| `GET /api/ask/stream` | 語音串流 |
| `POST /api/ai_push` | AI 推播（1 品） |
| `GET /api/assist_recommend` | 協助 Modal 推薦（3 品） |
| `POST /api/barrier_state` | 互動障礙狀態更新 |
| `POST /api/interaction_event` | POS 事件記錄 |
| `POST /api/intervention_result` | 介入結果回寫 |
| `POST /api/emotion/analyze_event` | Emotion-LLaMA 事件分析 |
| `GET /api/menu` | 菜單清單 |
| `POST /api/checkout` | 結帳（寫 log） |
| `GET /api/public_settings` | POS 可讀設定 |
| `GET/POST /api/settings` | 後台完整設定（8001） |
| `POST /api/session/mood` | 心情星星設定 |
| `WS /ws/{client_type}/{session_id}` | WebSocket（pos / admin） |

---

## 常用開發檢查

```bash
cd UI_API

# Python 語法
python3 -m py_compile main.py config.py
python3 -m py_compile backend/services/voice_service.py
python3 -m py_compile backend/services/emotion_service.py
python3 -m py_compile backend/routes/ai_push_routes.py

# JS 語法
node --check frontend/pos/app.js
node --check frontend/shared/api.js

# 服務確認
curl http://127.0.0.1:8000/api/public_settings
curl http://127.0.0.1:8001/api/settings
curl "http://127.0.0.1:8000/api/assist_recommend?session_id=test"
```
