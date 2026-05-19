# Project_2026

Project_2026 是一套智慧 POS 點餐與客服原型系統。專案目前包含兩個主要模組：

- `UI_API/`：FastAPI 後端、POS 前端、後台管理、RAG、語音點餐、AI 推播與客服流程。
- `Emotion-LLaMA/`：Emotion-LLaMA 推論服務，用於提供影像、語音情境與情緒行為證據。
- `Test/`：專利 PoC 與實施例測試腳本，可直接送事件到 UI_API。

本專案的核心方向不是單純做情緒辨識，而是：

> 事件觸發式多模態 POS 顧客互動障礙偵測與自適應服務介入系統

系統會先收集 POS 操作事件，計算互動障礙風險分數。只有當風險升高時，才觸發短片段多模態分析，將 POS 事件、UI context、語音文字、Emotion-LLaMA 分析與媒體訊號整合成 `barrier_state`，再轉換為可執行的 `intervention_action`。

---

## 主要功能

- POS 點餐介面
- 購物車與結帳流程
- 語音點餐與語音問答
- AI 餐點推播
- 客服浮動視窗與後台客服工作台
- Whisper 語音辨識與語系判斷
- Emotion-LLaMA 情緒與行為證據分析
- 客服狀態推理，將多模態證據轉成客服優先級與真人介入建議
- Ollama / Gemini API 問答
- 本地 RAG 文件與審查流程
- 互動事件風險分數
- `barrier_state` 互動障礙狀態推理
- `intervention_action` 服務介入決策
- 介入成效回饋與後台統計
- 事件觸發式多模態分析 API

---

## 專案結構

```text
Project_2026/
├── README.md
├── .gitignore
├── Emotion-LLaMA/
│   ├── app_EmotionLlamaClient.py
│   ├── eval_configs/
│   ├── emotion_llama/
│   └── ...
├── Test/
│   └── pos_interaction_demo_ui.py
└── UI_API/
    ├── main.py
    ├── ai_services.py
    ├── database.py
    ├── config.py
    ├── rag_service.py
    ├── index.html
    ├── PATENT_DESIGN.md
    ├── routes/
    ├── services/
    ├── repositories/
    ├── utils/
    ├── prompts/
    ├── static/
    ├── menu_data/
    ├── learning_data/
    ├── chroma_db_versions/
    ├── requirements.txt
    ├── requirements-lock.txt
    └── README.md
```

`UI_API/README.md` 是 UI_API 子系統的詳細文件；本 README 說明整個 Project_2026 的啟動、架構與專利化主軸。

---

## 系統架構

```text
POS 操作事件
  ↓
Interaction Event Engine
  ↓
互動障礙風險分數 risk_score
  ↓
是否達觸發門檻
  ↓
事件觸發式短片段多模態分析
  ├─ video / media_signals
  ├─ Whisper speech_text
  ├─ Emotion-LLaMA emotion evidence
  ├─ POS event sequence
  └─ UI context
  ↓
Barrier State Engine
  ↓
barrier_state
  ↓
Intervention Engine
  ↓
intervention_action
  ↓
checkout / payment feedback
```

Emotion-LLaMA 在此架構中不是決策核心，而是多模態證據來源之一。最終是否介入由 POS 操作事件、UI 狀態、語音內容、媒體訊號與風險分數共同決定。

---

## 環境需求

建議使用兩個 conda 環境分別啟動：

- `emotion_ollama`：啟動 Emotion-LLaMA 推論服務。
- `emotion_ui`：啟動 UI_API FastAPI 服務。

外部服務：

- Ollama
- Gemini API key，可選
- ngrok，可選

模型需求：

- Ollama model：`llama3.2`，可切換 `gemma4`
- Ollama embedding：`nomic-embed-text`
- Whisper
- Emotion-LLaMA 權重
- YOLO nano/person detection 權重，可選

大型權重檔、`.env`、執行紀錄與本機資料不應提交到 Git。

---

## 安裝

### UI_API

```bash
cd /home/oliver/Project_2026/UI_API
conda activate emotion_ui
pip install -r requirements.txt
```

正式部署若需要固定版本：

```bash
pip install -r requirements-lock.txt
```

### Ollama

```bash
ollama serve
ollama pull llama3.2
ollama pull gemma4
ollama pull nomic-embed-text
```

### Gemini API，可選

在 `UI_API/.env` 設定：

```env
GEMINI_API_KEY=你的 Gemini API Key
```

目前 AI 推播、RAG 審查與背景整理固定使用本地 Ollama；語音發問與客服回覆可在後台切換 Ollama 或 Gemini API。

---

## 啟動方式

### 1. 啟動 Emotion-LLaMA

```bash
cd /home/oliver/Project_2026/Emotion-LLaMA
conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

### 2. 啟動 UI_API

```bash
cd /home/oliver/Project_2026/UI_API
conda activate emotion_ui
python main.py
```

開啟：

```text
http://127.0.0.1:8000
```

若有設定 ngrok，終端機會顯示外網網址。若固定 ngrok endpoint 已被其他程序佔用，系統會略過 tunnel 並繼續啟動本機 API。

---

## UI_API 後端模組

```text
UI_API/
├── routes/
│   ├── core_routes.py                 # 首頁、checkout、設定
│   ├── menu_routes.py                 # 菜單管理
│   ├── rag_routes.py                  # RAG 文件與 PDF 匯入
│   ├── voice_routes.py                # 語音點餐與語音問答
│   ├── customer_service_routes.py     # 客服語音與真人回覆
│   ├── recommendation_routes.py       # AI 推播
│   ├── emotion_routes.py              # ping_state、影像片段、YOLO 偵測
│   ├── interaction_routes.py          # POS 操作事件、barrier、intervention
│   └── multimodal_routes.py           # 事件觸發式多模態分析
├── services/
│   ├── recommendation_service.py
│   ├── customer_service.py
│   ├── customer_service_state_service.py
│   ├── rag_review_service.py
│   ├── voice_order_service.py
│   ├── interaction_event_service.py
│   ├── barrier_state_service.py
│   ├── intervention_service.py
│   └── multimodal_evidence_service.py
└── repositories/
    ├── log_repository.py
    ├── menu_repository.py
    ├── session_repository.py
    ├── emotion_clip_repository.py
    └── interaction_event_repository.py
```

---

## 事件觸發式多模態分析

新增流程：

1. 前端上報 POS 操作事件到 `/api/interaction_event`。
2. 後端計算互動障礙風險分數。
3. 若達門檻，系統可先使用 `/api/barrier_state` 進行輕量狀態推理；若需要納入短片段影像、語音與 Emotion-LLaMA 證據，可呼叫 `/api/triggered_multimodal_analysis`。
4. `/api/triggered_multimodal_analysis` 只處理短片段，不做持續影像分析。
5. 後端整合：
   - recent POS events
   - risk_result
   - UI context
   - media_signals
   - Whisper speech_text
   - Emotion-LLaMA evidence
6. 產生 `multimodal_evidence`。
7. 推論 `barrier_state`。
8. 產生 `intervention_action`。
9. 若有有效介入，寫入 `intervention_logs.json`。
10. checkout 成功後回寫介入結果，形成成效回饋閉環。

`/api/triggered_multimodal_analysis` 會略過太小的 video chunk，避免空音訊或不完整片段造成推論錯誤。

### 實施例測試 UI

根目錄 `Test/pos_interaction_demo_ui.py` 會啟動一個本機 HTML 測試介面，可送出付款卡關、操作困惑、優惠券卡關與等待不耐等情境到 UI_API：

```bash
cd /home/oliver/Project_2026
python3 Test/pos_interaction_demo_ui.py
```

使用前請先啟動 `UI_API/main.py`。此腳本會開啟 `http://127.0.0.1:8765/`，瀏覽器按「送出事件」後會由腳本代理呼叫 `/api/interaction_event` 與 `/api/barrier_state`，送出後可自動開啟 `/?view=admin`。後台「互動障礙與介入成效」會透過輪詢更新，方便直接觀察操作行為、風險分數、互動障礙狀態與服務介入動作。

### 目前實作狀態

- `/api/interaction_event` 已串接 POS 操作事件。
- `/api/barrier_state` 已可做輕量互動障礙推理。
- `/api/triggered_multimodal_analysis` 已提供後端事件觸發式多模態分析能力。
- 前端可進一步串接 `triggered_multimodal_analysis`，使高風險事件直接觸發完整多模態證據分析。

---

## 主要 API 摘要

### POS / 基礎

- `GET /`
- `GET /api/menu`
- `POST /api/menu`
- `POST /api/checkout`
- `GET /api/settings`
- `POST /api/settings`

### 語音與客服

- `POST /api/ask`
- `POST /api/customer_service`
- `GET /api/customer_service_logs`
- `POST /api/customer_service_logs/{source_id}/human_reply`

客服流程會把 Whisper 語音文字、Emotion-LLaMA 結構化情緒、YOLO 人物偵測與媒體訊號轉成 `customer_service_state`。Emotion-LLaMA 在客服中不是單純做情緒辨識，而是提供多模態情緒與行為證據；系統再用該狀態決定客服優先級、真人介入建議與回覆策略。

後台客服系統會自動刷新客服紀錄。若關閉「Ollama 直接回覆」，API 會先立即回傳「已通知客服」，完整語音辨識、情緒證據與紀錄保存改由背景任務完成；該流程不再產生 AI 直接客服回答。

### RAG

- `GET /api/rag_docs`
- `POST /api/rag_docs`
- `DELETE /api/rag_docs/{doc_id}`
- `POST /api/rag_pdf`
- `DELETE /api/rag_docs`

### AI 推播

- `POST /api/auto_recommend`

### Emotion / 多模態

- `POST /api/ping_state`
- `POST /api/person_detect_frame`
- `GET /api/emotion_clips/{session_id}`
- `DELETE /api/emotion_clips/{session_id}`
- `POST /api/triggered_multimodal_analysis`

### 互動障礙與介入

- `POST /api/interaction_event`
- `GET /api/interaction_events/{session_id}`
- `POST /api/interaction_risk`
- `POST /api/barrier_state`
- `POST /api/intervention_result`
- `GET /api/intervention_logs/{session_id}`
- `GET /api/intervention_stats`

---

## 專利化技術重點

本系統可描述為一種低算力、低隱私風險的 POS 顧客互動障礙偵測與自適應服務介入架構。

技術特徵：

- 平時只記錄 POS 操作事件，不持續分析顧客影像。
- 使用 `risk_score` 判斷是否需要觸發多模態分析。
- 使用短片段分析，降低算力成本與隱私風險。
- Emotion-LLaMA 只提供情緒與行為證據，不直接決定服務策略。
- `barrier_state` 將情緒、語音、POS 操作與 UI 狀態轉成可控制的互動障礙狀態。
- `intervention_action` 將狀態轉成 UI 提示、付款教學、簡化模式、推播暫停或店員通知。
- `intervention_result` 在 checkout 時回寫，形成偵測、介入、成效回饋閉環。

詳細專利設計請看：

```text
UI_API/PATENT_DESIGN.md
```

---

## 隱私與低算力策略

系統支援以下設定：

```text
PRIVACY_SAVE_RAW_CLIP=false
PRIVACY_RAW_CLIP_RETENTION_MINUTES=10
PRIVACY_STORE_EVENT_VECTOR_ONLY=true
INTERACTION_TRIGGER_THRESHOLD=5
INTERACTION_PRE_EVENT_BUFFER_SEC=5
INTERACTION_POST_EVENT_BUFFER_SEC=5
```

設計原則：

- 平時只保存操作事件與匿名化事件向量。
- 可選擇不保存原始影像片段。
- 語音文字在 evidence 中會截斷，避免保存過長顧客內容。
- 只有風險達門檻才觸發短片段多模態分析。
- 後台統計以 `barrier_state`、`intervention_action` 與結果回饋為主。

---

## 開發與驗證

常用檢查：

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile ai_services.py
python3 -m py_compile routes/multimodal_routes.py
python3 -m py_compile services/multimodal_evidence_service.py
python3 -m py_compile services/barrier_state_service.py
python3 -m py_compile services/intervention_service.py
```

如果環境中沒有 `python` 指令，請使用 `python3`。

---
