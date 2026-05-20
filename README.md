# Project_2026

Project_2026 是一套智慧自助點餐與客服原型系統。系統整合 POS 點餐、語音點餐、客服、RAG、AI 推播、Whisper、Ollama、可選 Gemini API、YOLO 與 Emotion-LLaMA，並以「事件觸發式多模態 POS 顧客互動障礙偵測與自適應服務介入系統」作為目前的技術主軸。

本專案不是單純做情緒辨識。核心設計是先觀察 POS 操作事件與 UI 狀態，計算顧客是否可能卡關；只有當互動障礙風險升高時，才觸發短片段多模態分析，再把語音、影像、情緒證據、POS 事件與 UI context 轉換為可執行的服務介入動作。

---

## 目前入口

啟動 `UI_API/main.py` 後，系統會同時提供兩個入口：

```text
客戶端 POS：http://127.0.0.1:8000
後台管理：http://127.0.0.1:8001
```

若用主機 IP 或網域部署，對應為：

```text
客戶端 POS：http://<host>:8000
後台管理：http://<host>:8001
```

`0.0.0.0` 是服務綁定位址，代表接受所有網卡連線；瀏覽器通常使用 `127.0.0.1`、區網 IP 或網域名稱開啟。

前端會依照 port 自動判斷模式：

- `8000` 固定為客戶端 POS。
- `8001` 固定為後台管理。
- 即使在 `8000/admin`，前端仍只會顯示 POS，客戶端不能從 UI 切到後台。
- 即使在 `8001/pos`，前端仍會顯示後台。

---

## 專案模組

```text
Project_2026/
├── README.md
├── .gitignore
├── Emotion-LLaMA/
│   └── app_EmotionLlamaClient.py
├── tools/
│   └── pos_interaction_demo_ui.py
└── UI_API/
    ├── main.py
    ├── ai_services.py
    ├── database.py
    ├── rag_service.py
    ├── config.py
    ├── index.html
    ├── PATENT_DESIGN.md
    ├── routes/
    ├── services/
    ├── repositories/
    ├── realtime/
    ├── static/
    ├── menu_data/
    └── learning_data/
```

主要責任：

- `UI_API/`：FastAPI 後端、POS 前端、後台管理、語音點餐、客服、RAG、推播、互動障礙偵測、WebSocket 即時通訊。
- `Emotion-LLaMA/`：Emotion-LLaMA 推論服務，提供情緒與行為證據。
- `tools/`：專利 PoC 測試工具，可模擬付款失敗、優惠券錯誤、無效點擊、客服求助等事件。

---

## 使用流程

### 1. 啟動 Emotion-LLaMA

```bash
cd /home/oliver/Project_2026/Emotion-LLaMA
conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

Emotion-LLaMA 不是每次點擊都會被呼叫。預設策略是事件觸發：POS 風險升高或客服請求時才使用。

### 2. 啟動 Ollama

```bash
ollama serve
ollama pull llama3.2
ollama pull gemma4
ollama pull nomic-embed-text
```

預設 AI 來源：

- AI 推播：本地 Ollama。
- RAG 審查：本地 Ollama。
- 背景整理：本地 Ollama。
- 語音問答 / 客服回覆：預設本地 Ollama，可在後台切換 Gemini API。

### 3. 啟動 UI_API

```bash
cd /home/oliver/Project_2026/UI_API
conda activate emotion_ui
python main.py
```

開啟：

```text
POS：http://127.0.0.1:8000
後台：http://127.0.0.1:8001
```

### 4. POS 操作

1. 進入 `http://127.0.0.1:8000`。
2. 按「開始點餐」。
3. 選擇餐點類別與品項。
4. 加入購物車。
5. 進入購物車確認。
6. 前往付款頁。
7. 完成結帳後，系統回寫推播成效與介入成效。

POS UI 預設以 9:16 kiosk 比例排版，會依螢幕大小自動縮放。若螢幕較寬，POS 會保持直式 kiosk frame；若螢幕較窄，畫面會按高度與寬度等比縮放。

### 5. 後台操作

進入 `http://127.0.0.1:8001`。

後台可查看與管理：

- 儀表板與互動障礙介入成效。
- 功能模組開關。
- AI 參數。
- 情緒片段 / debug 分析。
- 菜單管理。
- RAG 文本與審查紀錄。
- 客服紀錄、顧客錄音、真人回覆。

後台不會自動啟動 POS 的 emotion loop、recommend loop、media recorder 或 interaction watcher。

---

## 系統邏輯

### 主流程

```text
POS 操作事件
  ↓
Interaction Event Engine
  ↓
risk_score + trigger_reasons
  ↓
是否達門檻
  ├─ 否：只保存低風險事件，不呼叫大型模型
  └─ 是：觸發短片段多模態分析
        ↓
        YOLO 人物偵測
        Whisper 語音轉文字
        media_signals 音量 / 靜音 / 動作訊號
        Emotion-LLaMA 情緒與行為證據
        POS event sequence
        UI context
        ↓
        multimodal_evidence
        ↓
        Barrier State Engine
        ↓
        Intervention Engine
        ↓
        WebSocket 推送 POS / Admin / Demo
        ↓
        checkout 後回寫 intervention_result
```

### 互動障礙狀態

`barrier_state` 用來描述顧客卡關型態，例如：

- `normal_operation`：正常操作
- `menu_hesitation`：菜單選擇猶豫
- `operation_confusion`：操作困惑
- `payment_confusion`：付款卡關
- `coupon_confusion`：優惠券或掃碼卡關
- `impatience_detected`：等待不耐
- `service_needed`：需要真人協助
- `potential_complaint`：疑似抱怨或客訴風險
- `low_confidence`：資訊不足

### 服務介入動作

`intervention_action` 是系統實際建議執行的服務行為，例如：

- 顯示付款教學。
- 顯示優惠券 / 掃碼教學。
- 顯示操作提示。
- 進入簡化介面。
- 推薦熱門組合。
- 暫停 AI 推播。
- 通知店員。
- 轉真人客服。

---

## 專利亮點與技術貢獻

### 1. 事件觸發，而非持續監控

傳統情緒辨識系統容易持續分析影像，造成算力負擔與隱私風險。本系統先使用 POS 操作事件計算風險，只有風險達門檻才觸發多模態分析。

技術效果：

- 降低 GPU / CPU 持續推論成本。
- 減少原始影像保存需求。
- 避免對正常顧客操作進行不必要分析。

### 2. 從 emotion_label 轉換為 barrier_state

本系統不把「情緒標籤」當成最終結論。Emotion-LLaMA 只提供情緒與行為證據；系統再融合 POS 操作事件、UI context 與語音內容，推論可操作的 `barrier_state`。

技術效果：

- 情緒分析不再停留於「生氣 / 平靜 / 困惑」。
- 可轉換為付款教學、操作提示、店員通知等具體 POS 控制策略。

### 3. 多模態證據融合

系統建立 `multimodal_evidence`，內容包含：

- `visual_evidence`：人物偵測、人物框、畫面是否有人。
- `audio_evidence`：語音文字、是否靜音、音量資訊。
- `emotion_evidence`：Emotion-LLaMA 情緒與行為證據。
- `pos_evidence`：頁面、風險分數、觸發原因、事件摘要。

技術效果：

- 降低單一情緒模型誤判造成的錯誤介入。
- 當沒有偵測到人物或影片不可讀時，可降低情緒權重並 fallback 到 POS 事件推理。

### 4. 自適應服務介入

系統會根據 `barrier_state` 產生 `intervention_action`，並透過 WebSocket 即時推送到 POS 和後台。

技術效果：

- 顧客卡關時，POS 可以立即顯示協助內容。
- 後台可同步收到店員通知。
- 可區分付款卡關、優惠券卡關、操作困惑、等待不耐與客訴風險。

### 5. 成效回饋閉環

checkout 完成後，系統會把最近尚未結案的介入紀錄更新為：

- `checkout_success`
- `payment_success`
- `time_to_checkout_sec`
- `resolved_by_checkout`

技術效果：

- 可統計介入成功率。
- 可評估哪些頁面最容易造成卡關。
- 可作為後續調整門檻與策略的技術依據。

---

## 隱私與低算力策略

預設策略：

- 平時只保存 POS 操作事件。
- 不長期保存原始影像。
- 只在高風險事件時擷取短片段。
- 語音文字與 evidence 會截斷，避免保存過長顧客內容。
- 可只保存匿名化事件向量、`barrier_state` 與 `intervention_result`。

重要設定：

```text
EVENT_TRIGGERED_MULTIMODAL_ENABLED=true
EMOTION_PERIODIC_ENABLED=false
INTERACTION_TRIGGER_THRESHOLD=5
INTERACTION_PRE_EVENT_BUFFER_SEC=5
INTERACTION_POST_EVENT_BUFFER_SEC=5
PRIVACY_SAVE_RAW_CLIP=false
PRIVACY_STORE_EVENT_VECTOR_ONLY=true
```

---

## 實施例測試工具

啟動測試 UI：

```bash
cd /home/oliver/Project_2026
python3 tools/pos_interaction_demo_ui.py
```

建議流程：

1. 啟動 UI_API。
2. 開啟 POS：`http://127.0.0.1:8000/pos?session_id=pos_demo_001`
3. 開啟後台：`http://127.0.0.1:8001`
4. 在測試工具中保持 `session_id=pos_demo_001`。
5. 按「付款失敗」、「優惠券錯誤」、「無效點擊」等按鈕。
6. 觀察 POS 是否收到 intervention。
7. 觀察後台是否更新介入統計。

---

## 相關文件

- `UI_API/README.md`：UI_API 詳細架構、API、資料檔與使用流程。
- `UI_API/PATENT_DESIGN.md`：專利設計草稿、技術問題、技術手段、請求項概念稿。

---

## 版本控制注意事項

不應提交：

- `.env`
- 模型權重
- ChromaDB runtime 版本資料
- `learning_data/` runtime log
- `__pycache__/`

目前 `.gitignore` 已排除這些資料。新增模型或本機測試檔時，請先確認不含 API key、權重或個資。
