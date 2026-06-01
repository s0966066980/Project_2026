# Project_2026

智慧自助點餐 kiosk 原型系統（麥當勞台灣 PoC），以「事件觸發式多模態 POS 顧客互動障礙偵測與自適應服務介入系統」作為技術主軸。

---

## 目前版本功能

### POS 端（客戶操作介面）

- **選單點餐**：分類瀏覽菜單、加入購物車、結帳付款，支援全螢幕 Kiosk 16:9 佈局
- **語音協助**（`voiceAssist`）：按下語音按鈕後全螢幕收音，Whisper STT → Ollama LLM → Edge TTS，可直接操作購物車
- **AI 推播推薦**：定期呼叫 Ollama 選 1 品，底部浮卡顯示推薦 + 促購短句
- **猶豫彈跳視窗**：購物車空且無操作 60 秒後觸發推薦彈窗
- **互動障礙偵測**：POS 操作事件（付款失敗、停留時間等）→ `barrier_state` → 介入決策 → WebSocket 推送介入卡

### 後台（Admin 管理介面）

- **儀表板**：介入成效統計、推播命中率、障礙分布圖
- **功能開關**：語音、AI 推播、Emotion-LLaMA、RAG 等功能即時切換
- **AI 設定**：Ollama 模型、STT/TTS 設定、各項 System Prompt 調整
- **Emotion-LLaMA 設定**：啟用事件分析、片段時長、品質快篩、結果注入開關 + 介入紀錄表
- **菜單管理**：直接編輯 `menu.json`

---

## Tech Stack

| 元件 | 說明 |
|---|---|
| 後端 | Python 3.x、FastAPI（同時啟動 port 8000 / 8001） |
| 前端 | Vanilla JS（app.js、api.js、cart.js、media.js 等），無框架 |
| STT | faster-whisper（本地，`small` 模型，可切換 openai-compatible） |
| TTS | MeloTTS（預設）、Edge TTS、openai-compatible |
| LLM | Ollama `qwen3.5:4b`（推播 + 語音協助） |
| 情緒分析 | Emotion-LLaMA（port 7889，事件觸發式，可選） |
| RAG | fastembed `BAAI/bge-small-zh-v1.5`（可選，無文件時自動跳過） |
| 選用 | Gemini API（可替換 LLM 來源） |
| 設定 | `.env` + `learning_data/settings.json`（後台即時讀寫） |

---

## 啟動方式

```bash
# 必要：Ollama
ollama serve
ollama pull qwen3.5:4b

# 主服務
cd UI_API && conda activate emotion_ui
python main.py
# POS：http://127.0.0.1:8000
# 後台：http://127.0.0.1:8001

# 可選：Emotion-LLaMA（事件分析用）
cd Emotion-LLaMA && conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

---

## 專案結構

```text
Project_2026/
├── CLAUDE.md                        ← 開發規則與架構說明
├── Emotion-LLaMA/
│   └── app_EmotionLlamaClient.py    ← 情緒推論服務（port 7889，可選）
└── UI_API/
    ├── main.py                       ← 唯一入口，同時啟動 8000/8001
    ├── config.py                     ← 靜態設定 + 動態設定管理器
    ├── backend/
    │   ├── ai_services.py            ← Whisper、Ollama、Gemini、TTS
    │   ├── database.py               ← 菜單 context、checkout log
    │   ├── routes/                   ← FastAPI endpoints
    │   ├── services/                 ← 業務邏輯
    │   ├── repositories/             ← JSON 資料存取
    │   ├── realtime/                 ← WebSocket event bus
    │   ├── utils/                    ← 共用工具
    │   └── prompts/defaults.py       ← LLM system prompt 預設值
    ├── frontend/
    │   ├── pos/                      ← POS kiosk（index.html, app.js, cart.js, media.js）
    │   ├── admin/                    ← 後台（admin.html, admin.js）
    │   └── shared/                   ← 共用（api.js, ui.js, realtime_client.js）
    ├── learning_data/                ← Runtime 資料（不提交 git）
    └── menu_data/menu.json           ← 菜單（MCDxxx 格式）
```

---

## 核心業務流程

### 互動障礙介入

```text
POS 操作事件（點擊、付款失敗、停留等）
  → POST /api/interaction_event
語音輸入 / 手動觸發
  → POST /api/barrier_state
    → barrier_state_service（POS 事件計數 + 語音關鍵字）
    → intervention_service（barrier_state → action）
    → WebSocket 推送介入卡給 POS
結帳後回寫 intervention_result（閉環）
```

### 語音點餐

```text
麥克風錄音 → POST /api/ask
  → Whisper STT → Ollama LLM → Edge TTS
  → cart_actions 加入購物車 + 語音回覆
```

### Emotion-LLaMA 事件分析（可選）

```text
「如何點餐」彈跳視窗觸發
  → rolling buffer 截取前 N 秒影片
  → POST /api/emotion/analyze_event
    → 非同步呼叫 Gradio API（port 7889）
    → 結果寫入 emotion_intervention_logs.json
    → 可選：注入下一輪語音 prompt / 觸發 barrier pipeline
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

## 相關文件

- `CLAUDE.md`：架構規則、禁止事項、開發檢查指令
- `UI_API/README.md`：API 完整清單、前後端架構說明
- `UI_API/CODEBASE.md`：每個檔案的職責與程式碼架構詳細說明
- `UI_API/ARCHITECTURE_MAPPING.md`：架構層對應說明（程式碼 ↔ 流程）
- `UI_API/PATENT_DESIGN.md`：專利設計草稿
