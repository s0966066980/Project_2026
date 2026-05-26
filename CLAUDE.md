# Project_2026 — 智慧自助點餐與客服介入系統

## 專案概述

這是一套以「事件觸發式多模態 POS 顧客互動障礙偵測與自適應服務介入系統」為技術主軸的智慧自助點餐原型系統。  
**核心邏輯**：先觀察 POS 操作事件計算 `risk_score`，風險達門檻才觸發短片段多模態分析，最後產生可執行的服務介入動作（`intervention_action`）。  
Emotion-LLaMA 只是多模態證據來源之一，**不是**系統的決策核心。

---

## Tech Stack

- **後端**：Python 3.x、FastAPI（同時啟動 port 8000 和 8001）
- **前端**：Vanilla JS（app.js、api.js、cart.js、ui.js、media.js 等），無前端框架
- **AI 推論**：Ollama（qwen3.5:4b、nomic-embed-text）、可選 Gemini API
- **語音**：Whisper（本地）、Edge TTS
- **視覺**：YOLO（人物偵測）、Emotion-LLaMA（情緒與行為證據，port 7889）
- **資料庫**：ChromaDB（RAG 向量庫）、JSON 檔（session/log/menu）
- **設定**：`.env` + `learning_data/settings.json`（後台可即時讀寫）

---

## 專案結構

```
Project_2026/
├── README.md
├── CLAUDE.md
├── Emotion-LLaMA/
│   └── app_EmotionLlamaClient.py   ← 情緒推論服務，port 7889
├── tools/
│   └── pos_interaction_demo_ui.py  ← 專利 PoC 測試工具
└── UI_API/
    ├── main.py                     ← 唯一入口，同時啟動 8000/8001
    ├── config.py                   ← 靜態設定 + 動態設定管理器
    ├── ai_services.py              ← Whisper、Ollama、Gemini、TTS、YOLO 呼叫
    ├── rag_service.py              ← ChromaDB、LangChain RAG
    ├── database.py
    ├── prompts/defaults.py         ← 所有 system prompt 預設值
    ├── routes/                     ← FastAPI endpoint（只解析請求，呼叫 service）
    ├── services/                   ← 業務邏輯
    ├── repositories/               ← JSON 資料存取
    ├── realtime/                   ← WebSocket event bus
    ├── utils/
    ├── static/                     ← 前端 JS/CSS/圖片
    ├── menu_data/menu.json         ← 正式菜單（麥當勞台灣品項）
    └── learning_data/              ← Runtime 資料（不提交 git）
```

---

## 啟動方式

```bash
# 1. 啟動 Emotion-LLaMA（若需要情緒分析）
cd Emotion-LLaMA && conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889

# 2. 啟動 Ollama
ollama serve
ollama pull llama3.2 && ollama pull nomic-embed-text

# 3. 啟動主服務
cd UI_API && conda activate emotion_ui
python main.py
# POS：http://127.0.0.1:8000
# 後台：http://127.0.0.1:8001
```

---

## 架構規則（修改前必讀）

### 分層職責
- **routes/**：只做請求解析、呼叫 service、回傳 response。**不放業務邏輯。**
- **services/**：業務邏輯主體。不直接讀寫 JSON 檔，透過 repository。
- **repositories/**：JSON 資料存取。**不放業務邏輯、不做 AI 呼叫。**
- **ai_services.py**：所有 AI 呼叫（Whisper、Ollama、Gemini、TTS、YOLO、Emotion-LLaMA）集中在此。

### 設定系統
- 靜態設定（port、API key、網域）寫在 `.env`，由 `config.py` 讀取。
- 動態設定（AI 參數、功能開關）存在 `learning_data/settings.json`，後台可即時修改。
- **讀設定統一用 `config.get("KEY")`**，不要直接讀 `os.getenv`。
- `DEFAULT_SETTINGS` 在 `config.py` 定義，新增設定先加到這裡。

### 菜單白名單
- 菜單資料來源：`menu_data/menu.json`（品項 ID 格式：`MCDxxx`）。
- 語音點餐、AI 推播的品項必須通過菜單白名單校正，**不允許 LLM 幻覺出不存在的餐點**。
- 菜單圖片直接引用麥當勞台灣線上 URL，不要本地化。

### RAG 原則
- RAG 只補充政策、規則、客服話術、套餐說明，**不取代菜單白名單**。
- `manual` 類型 RAG 會當成全域規則注入，不依相似度命中。
- 若 RAG 檢索分數不足或與問題無關，強制回答「目前文件沒有足夠資訊」，**不允許 LLM 自行發揮**。

### WebSocket
- 統一入口：`/ws/{client_type}/{session_id}`
- `client_type`：`pos`、`admin`、`demo`、`emotion`
- 事件推送透過 `realtime/event_bus.py`，**不在 route 或 service 直接操作 WebSocket 連線**。

### port 隔離
- port 8000：永遠是 POS 客戶端，即使進入 `/admin` 也不改變。
- port 8001：永遠是後台管理，即使進入 `/pos` 也不改變。
- **不要修改這個邏輯。**

---

## 禁止事項（不要做）

- **不要修改 `learning_data/` 的資料結構**（session_logs、intervention_logs、customer_service_logs），除非同步更新 repository 的讀寫邏輯。
- **不要在 route 直接呼叫 ai_services**，一律透過 service layer。
- **不要在 service 直接讀寫 JSON 檔**，透過 repository。
- **不要讓 Emotion-LLaMA 的情緒標籤直接決定介入動作**，必須先通過 `barrier_state_service` 轉換。
- **不要在 checkout 流程加入阻擋邏輯**，checkout 應永遠可以完成。
- **不要提交 `.env`、模型權重、`learning_data/` runtime 資料、`chroma_db/`。**
- **不要修改菜單 JSON 的 ID 格式（MCDxxx）**，前端、後端、RAG 都依賴此格式。

---

## 核心業務流程

```
POS 操作事件 → interaction_event_service（計算 risk_score）
  → risk_score.triggered = true
  → triggered_multimodal_analysis（YOLO + Whisper + Emotion-LLaMA）
  → multimodal_evidence_service（整合四類證據）
  → barrier_state_service（推理 barrier_state）
  → intervention_service（決定 intervention_action）
  → WebSocket 推送 POS / Admin / Demo
  → checkout 後回寫 intervention_result（閉環）
```

---

## 目前 barrier_state 與 intervention_action 對照

| barrier_state | 常見 intervention_action |
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

## Emotion Risk Score 規則

| 分數 | level | 行為 |
|---|---|---|
| 1-2 | stable | 只保存觀察 |
| 3-4 | watch | 持續觀察 |
| 5-6 | assist | 顯示輔助訊息 |
| 7-8 | urgent | 優先安撫、通知店員 |
| 9-10 | critical | 立即通知真人、停止推銷 |

基礎分數邏輯在 `services/emotion_risk_service.py`，語音內容含客訴/付款失敗/不會操作會加權。

---

## 常用開發檢查

```bash
# Python 語法檢查
python3 -m py_compile UI_API/main.py UI_API/config.py UI_API/ai_services.py
python3 -m py_compile UI_API/routes/multimodal_routes.py
python3 -m py_compile UI_API/services/barrier_state_service.py UI_API/services/intervention_service.py

# JS 語法檢查
node --check UI_API/static/app.js
node --check UI_API/static/api.js
node --check UI_API/static/media_buffer.js

# 啟動後確認兩個 port 都正常
curl http://127.0.0.1:8000/api/settings
curl http://127.0.0.1:8001/api/settings
```

---

## 目前 Sprint / 進行中工作

<!-- > 此區塊請隨時更新，讓 Claude Code 知道目前聚焦在哪裡。

- [ ] （請填入目前正在開發的功能或修復的 bug）
- [ ] （例如：優化 barrier_state 推理邏輯、新增 coupon_confusion 場景支援等） -->
- 優化程式碼，讓程式碼呈現易讀


---

## 相關文件

- `README.md`：系統概述、啟動流程、完整系統邏輯、外網部署說明
- `UI_API/README.md`：UI_API 詳細架構、所有 API 清單、POS 與後台使用流程
- `UI_API/PATENT_DESIGN.md`：專利設計草稿、技術問題、技術手段、請求項概念稿
- `UI_API/ARCHITECTURE_MAPPING.md`：架構對應說明
