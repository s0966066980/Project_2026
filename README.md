# Project_2026

Project_2026 是一套智慧自助點餐原型系統，以「事件觸發式多模態 POS 顧客互動障礙偵測與自適應服務介入系統」作為技術主軸。

系統的核心邏輯是：先觀察 POS 操作事件計算 `risk_score`，風險達門檻才觸發短片段多模態分析，再把語音、影像、情緒證據、POS 事件與 UI context 轉換為可執行的服務介入動作（`intervention_action`）。Emotion-LLaMA 是多模態證據來源之一，**不是**系統的決策核心。

---

## 目前版本功能

### POS 端（客戶操作介面）

- **選單點餐**：分類瀏覽菜單、加入購物車、結帳付款，支援全螢幕 Kiosk 16:9 佈局與行動版 Fluid 佈局。
- **語音協助**（`voiceAssist`）：點選底部「語音模式」按鈕進入語音模式。按下後出現全螢幕收音 overlay，含聲波動畫與麥克風圖示。按住叉叉按鈕 0.4 秒關閉收音。語音送出後，Whisper 轉文字，qwen3.5:9b 負責意圖理解（點餐 / 問答），TTS 語音回覆，可直接操作購物車。
- **AI 推播推薦**：計時器定期以 qwen3.5:4b 根據菜單與 RAG 規則推薦 1\~3 道餐點，以底部透明浮卡顯示，5 秒自動消失。後台可切換「Ollama AI 推薦」或「預設熱門推薦」。
- **無效點擊偵測**：連續 3 次在 4 秒內點擊非互動區域，才觸發操作教學提示（不會在正常點餐流程中干擾顧客）。
- **多語支援**：中文 / 英文介面切換。

### 後台（Admin 管理介面）

- **儀表板**：介入成效統計、推播命中率、互動障礙分佈。
- **功能模組**：即時開關各功能（情緒偵測、語音協助、AI 推播、Emotion-LLaMA 等）。
- **Emotion 功能**：情緒分析參數、人物偵測設定。
- **AI 設定**：Ollama 模型、RAG 參數、各項 System Prompt 調整、推播 / 語音協助 Prompt。
- **語音協助**：語音協助模型（預設 qwen3.5:9b）與 System Prompt 設定。
- **影像片段**：查看與清除本訂單的情緒分析影片片段。
- **菜單管理**：直接編輯 `menu.json`（JSON 格式）。
- **RAG 文本**：上傳 PDF / 手動新增規則、觸發審查與向量庫重建、查看審查紀錄。

---

## Tech Stack

| 元件 | 說明 |
|---|---|
| 後端 | Python 3.x、FastAPI（同時啟動 port 8000 / 8001） |
| 前端 | Vanilla JS（app.js、api.js、cart.js、ui.js、media.js 等），無框架 |
| 語音辨識 | Whisper（本地，僅在語音協助與多模態分析時呼叫） |
| 語音回覆 | Edge TTS |
| 語音協助 AI | Ollama qwen3.5:9b（獨立模型，不影響推播） |
| AI 推播 AI | Ollama qwen3.5:4b |
| Embedding / RAG | nomic-embed-text、ChromaDB、LangChain |
| 情緒分析 | Emotion-LLaMA（port 7889，只在高風險事件或語音協助時介入） |
| 選用 | Gemini API（可替換語音問答 AI 來源） |
| 設定 | `.env` + `learning_data/settings.json`（後台即時讀寫） |

---

## 入口

啟動 `UI_API/main.py` 後，系統同時提供：

```text
客戶端 POS：http://127.0.0.1:8000
後台管理：http://127.0.0.1:8001
```

前端依 port 自動判斷模式：
- `8000` 固定為客戶端 POS
- `8001` 固定為後台管理

---

## 啟動方式

```bash
# 1. 啟動 Emotion-LLaMA（需要情緒分析時）
cd Emotion-LLaMA && conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889

# 2. 啟動 Ollama（系統會自動呼叫 ollama serve 與 pull 模型）
ollama serve
ollama pull qwen3.5:4b
ollama pull qwen3.5:9b
ollama pull nomic-embed-text

# 3. 啟動主服務
cd UI_API && conda activate emotion_ui
python main.py
```

系統啟動時會自動偵測 Ollama 是否在線，並在背景 pull 所需模型（`qwen3.5:4b`、`qwen3.5:9b`、`nomic-embed-text`）。

---

## 專案結構

```text
Project_2026/
├── README.md
├── CLAUDE.md                        ← 開發規則與架構說明
├── .gitignore
├── Emotion-LLaMA/
│   └── app_EmotionLlamaClient.py   ← 情緒推論服務（port 7889）
├── tools/
│   └── pos_interaction_demo_ui.py  ← 專利 PoC 測試工具
└── UI_API/
    ├── main.py                      ← 唯一入口，同時啟動 8000/8001
    ├── config.py                    ← 靜態設定 + 動態設定管理器
    ├── ai_services.py               ← Whisper、Ollama、Gemini、TTS、Emotion-LLaMA
    ├── rag_service.py               ← ChromaDB、LangChain RAG
    ├── database.py
    ├── index.html                   ← POS + Admin 單頁應用
    ├── prompts/defaults.py          ← 所有 system prompt 預設值
    ├── routes/                      ← FastAPI endpoint（只解析請求）
    ├── services/                    ← 業務邏輯
    ├── repositories/                ← JSON 資料存取
    ├── realtime/                    ← WebSocket event bus
    ├── utils/
    ├── static/                      ← 前端 JS / CSS
    ├── menu_data/menu.json          ← 正式菜單（麥當勞台灣品項）
    └── learning_data/               ← Runtime 資料（不提交 git）
```

---

## 系統邏輯

### 主流程（互動障礙偵測）

```text
POS 操作事件
  ↓
Interaction Event Engine（計算 risk_score）
  ↓
  ├─ risk_score 未達門檻 → 只記錄，不呼叫大型模型
  └─ risk_score 達門檻 → 觸發短片段多模態分析
        ↓
        Whisper 語音轉文字
        Emotion-LLaMA 情緒與行為證據
        POS event sequence + UI context
        ↓
        multimodal_evidence（四類證據融合）
        ↓
        Barrier State Engine → barrier_state
        ↓
        Intervention Engine → intervention_action
        ↓
        WebSocket 推送 POS / Admin / Demo
        ↓
        checkout 後回寫 intervention_result（閉環）
```

### 語音協助流程

```text
顧客按「語音模式」按鈕
  ↓
全螢幕 overlay 出現（聲波動畫）
  ↓
MediaRecorder 錄音
  ↓
按住叉叉 0.4 秒 → 停止錄音
  ↓
/api/ask（Whisper STT + qwen3.5:9b 意圖分析）
  ↓
點餐 → 操作購物車（cart_actions）
問答 → TTS 語音回覆 + AI 氣泡顯示
  ↓
觸發推薦評估（可選）
```

### AI 推播推薦流程

```text
recommendLoop（定期觸發，預設 30 秒間隔）
  ↓
USE_AI_RECOMMEND=true → qwen3.5:4b（菜單 + RAG 規則）
USE_AI_RECOMMEND=false → 預設熱門推薦
  ↓
底部透明浮卡顯示（1~3 道餐點 + 原因）
5 秒自動消失 / 可加入購物車
```

---

## 互動障礙狀態與介入對照

| barrier_state | 說明 | 常見 intervention_action |
|---|---|---|
| `normal_operation` | 正常操作 | `none` |
| `menu_hesitation` | 菜單選擇猶豫 | `recommend_popular_combo` |
| `operation_confusion` | 操作困惑 | `show_operation_hint` |
| `payment_confusion` | 付款卡關 | `show_payment_tutorial` |
| `coupon_confusion` | 優惠券卡關 | `show_coupon_guide` |
| `impatience_detected` | 等待不耐 | `call_staff_or_fast_mode` |
| `service_needed` | 需要協助 | `call_staff` |
| `potential_complaint` | 疑似客訴風險 | `call_staff` |
| `low_confidence` | 資訊不足 | `ask_clarifying_question` |

---

## Emotion Risk Score

| 分數 | Level | 行為 |
|---|---|---|
| 1-2 | stable | 只保存觀察 |
| 3-4 | watch | 持續觀察 |
| 5-6 | assist | 顯示輔助訊息 |
| 7-8 | urgent | 優先安撫、通知店員 |
| 9-10 | critical | 立即通知真人、停止推播推薦 |

---

## 隱私與算力策略

- 平時只保存 POS 操作事件，不持續分析影像。
- 只在高風險事件時擷取短片段（`INTERACTION_PRE_EVENT_BUFFER_SEC`）。
- 語音協助 Whisper 只在顧客主動按下語音按鈕後才呼叫，不持續監聽。
- 事件觸發多模態分析的 Whisper 只分析已觸發片段的音訊。
- 語音文字與 evidence 截斷，避免保存過長顧客內容。

關鍵設定：

```text
EVENT_TRIGGERED_MULTIMODAL_ENABLED=true
EMOTION_PERIODIC_ENABLED=false
INTERACTION_TRIGGER_THRESHOLD=5
PRIVACY_SAVE_RAW_CLIP=false
PRIVACY_STORE_EVENT_VECTOR_ONLY=true
```

---

## 外網部署（ngrok / 反向代理）

```env
DEMO_PUBLIC_MODE=true
POS_DEMO_TOKEN=<POS token>
ADMIN_DEMO_TOKEN=<Admin token>
WS_DEMO_TOKEN=<WebSocket token>
PUBLIC_POS_ORIGIN=https://<ngrok-url>
ENABLE_NGROK=true
NGROK_AUTHTOKEN=<ngrok token>
```

外網訪問時建議 URL 帶 token：

```text
POS：https://<ngrok-url>/pos?token=<POS_DEMO_TOKEN>
Admin：https://<ngrok-url>/admin?token=<ADMIN_DEMO_TOKEN>
```

安全原則：
- Admin API 在 `DEMO_PUBLIC_MODE=true` 時需要 `X-Admin-Token` 或 URL `?token=`。
- POS 必要 API 不擋 token，避免點餐流程中斷。
- 語音協助紀錄預設不寫入 RAG，避免外網測試個資污染知識庫。

---

## 測試工具

```bash
# 啟動 PoC demo 工具（開啟瀏覽器）
python3 tools/pos_interaction_demo_ui.py
```

或直接開啟：`http://127.0.0.1:8000/demo-tool`

Demo 工具可模擬五種情境：不會操作、無法決定餐點、付款失敗、客訴風險、低風險正常操作。

建議測試流程：
1. 啟動 UI_API
2. POS：`http://127.0.0.1:8000/pos?session_id=pos_demo_001`
3. Admin：`http://127.0.0.1:8001`
4. demo-tool 中選 `session_id=pos_demo_001` 後觸發情境
5. 觀察 POS 介入提示與 Admin 統計更新

---

## 版本控制注意事項

不應提交：

- `.env`
- 模型權重
- `learning_data/` runtime log（session、intervention、rag 向量）
- `chroma_db/`
- `__pycache__/`

---

## 相關文件

- `CLAUDE.md`：架構規則、禁止事項、開發檢查指令。
- `UI_API/README.md`：UI_API 詳細架構、API 清單、資料結構說明。
- `UI_API/PATENT_DESIGN.md`：專利設計草稿、技術問題與請求項。
- `UI_API/ARCHITECTURE_MAPPING.md`：架構層對應說明。
