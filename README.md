# Project_2026

Project_2026 是一套智慧自助點餐與客服原型系統。系統整合 POS 點餐、語音點餐、客服、RAG、AI 推播、Whisper、Ollama、可選 Gemini API、YOLO 與 Emotion-LLaMA，並以「事件觸發式多模態 POS 顧客互動障礙偵測與自適應服務介入系統」作為目前的技術主軸。

本專案不是單純做情緒辨識。核心設計是先觀察 POS 操作事件與 UI 狀態，計算顧客是否可能卡關；只有當互動障礙風險升高時，才觸發短片段多模態分析，再把語音、影像、情緒證據、POS 事件與 UI context 轉換為可執行的服務介入動作。

---

## 2026/05/21 系統更新筆記



**1. POS UI 響應式佈局 (Responsive Layout)**

- 橫式大螢幕 (Landscape)：維持 16:9 固定比例 (Kiosk Width/Height)。

- 直立與行動版 (Portrait & Mobile)：自動切換為 Fluid 佈局 (width: 100%, 高度自適應)，支援垂直滾動，開始點餐按鈕將直接顯示以利小螢幕點擊。



**2. RAG 與語音點餐優化**

- llama3.2 等本地小模型對於事實核對能力較弱。系統新增**嚴格來源限制**與**答案驗證**機制。

- 只要 RAG 檢索的最高分數與關鍵字重疊度未達標準，或是 LLM 生成內容包含來源沒有的數字與價格，系統將會啟動防護，強制回答「目前文件沒有足夠資訊回答」。

- 在後台可以查看詳細的「RAG 檢索狀態」，包括 Answerability 評估結果與 Quality Gate 的阻擋原因。

---

## 2026/05/25 除錯與規則更新

**1. Whisper 語音辨識防誤判**

- 新增最短有效語音長度、音量門檻、Whisper `no_speech_prob`、`avg_logprob`、`compression_ratio` 過濾。
- 前端語音按鍵低於 650ms 或錄音資料過小時不送出，避免誤觸與空白音訊造成 Whisper 幻覺文字。
- Whisper prompt 加入繁體中文點餐常見詞，降低「大麥克、薯條、推薦、付款、客服」等 kiosk 場景詞被辨識錯的機率。

**2. 推薦餐點問答改走 RAG + 基礎 LLM**

- 顧客明確詢問「推薦餐點」時，現在優先走 `ASK` 問答路徑：完整菜單白名單 + RAG 全域規則/補充內容 + 本地 Ollama。
- 若 RAG 沒有相關補充，仍會用完整菜單白名單和基礎 LLM 產生推薦，不再直接輸出通用預設回覆。
- 主動推播推薦保留為備援；只有 RAG/ASK LLM 無法產生有效回答時才回落。

**3. Emotion-LLaMA 風險分數 1~10**

Emotion-LLaMA 現在會被轉成可解釋的 `emotion_risk_score`，並提供 `emotion_risk_level`、`emotion_risk_evidence` 與固定規則表：

| 分數 | 等級 | 規則 |
| --- | --- | --- |
| 1-2 | stable | 顧客穩定或低信心無人狀態，只保存觀察。 |
| 3-4 | watch | 輕微疲憊、猶豫或不確定，持續觀察。 |
| 5-6 | assist | 困惑、操作/付款問題或中度負面訊號，顯示輔助。 |
| 7-8 | urgent | 焦躁、急迫、等待太久等高風險訊號，優先安撫並可通知店員。 |
| 9-10 | critical | 生氣、客訴或強烈負面訊號，立即通知真人店員，停止推銷式推薦。 |


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
- `tools/`：專利 PoC 測試工具。`pos_interaction_demo_ui.py` 內嵌 `/demo-tool` HTML，執行後會直接開啟瀏覽器測試介面。

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

POS UI 預設以 16:9 kiosk 比例排版，會依螢幕大小自動縮放。若螢幕比例不同，畫面會在可視範圍內等比置中。

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

目前正式菜單使用 `UI_API/menu_data/menu.json`，已整理為麥當勞台灣品項資料。品項圖片直接引用麥當勞台灣
完整菜單頁的線上圖片 URL，避免本機圖片與官方內容不同步。RAG 可額外匯入 PDF，例如超值全餐規則或活動說明；
菜單問答仍以菜單 JSON 白名單為主，RAG 作為政策、規則與補充資料。

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

HTML 測試工具：

```text
http://127.0.0.1:8000/demo-tool
```

Demo 工具會呼叫 `/api/demo/trigger_scenario`、`/api/triggered_multimodal_analysis` 與 `/api/auto_recommend`，並透過 `/ws/demo/{session_id}` 監聽即時介入事件；目前只保留專利 PoC 需要的問題：操作困惑、付款卡關、優惠券卡關、客訴風險、短片段 fallback 與主動推薦。

建議流程：

1. 啟動 UI_API。
2. 開啟 POS：`http://127.0.0.1:8000/pos?session_id=pos_demo_001`
3. 開啟後台：`http://127.0.0.1:8001`
4. 在測試工具中保持 `session_id=pos_demo_001`。
5. 按「付款失敗」、「優惠券錯誤」、「無效點擊」等按鈕。
6. 觀察 POS 是否收到 intervention。
7. 觀察後台是否更新介入統計。

---

## 外網客戶測試

外網 demo 建議使用反向代理或 ngrok 分別公開 POS 與 Admin：

```text
POS 測試網址：https://<public-pos-domain>?token=<POS_DEMO_TOKEN>
Admin 測試網址：https://<public-admin-domain>?token=<ADMIN_DEMO_TOKEN>
WebSocket：瀏覽器會自動使用 wss://<domain>/ws/...
```

`.env` 建議設定：

```env
DEMO_PUBLIC_MODE=true
POS_DEMO_TOKEN=請填 POS/demo token
ADMIN_DEMO_TOKEN=請填後台 token
WS_DEMO_TOKEN=可選的共用 websocket token
PUBLIC_POS_ORIGIN=https://<public-pos-domain>
PUBLIC_ADMIN_ORIGIN=https://<public-admin-domain>
ENABLE_NGROK=false
```

若要只公開客戶端 POS，可設定：

```env
ENABLE_NGROK=true
NGROK_AUTHTOKEN=你的 ngrok token
```

啟動後系統只會替 POS port 建立 tunnel；Admin 仍建議走獨立受控網址並使用 `ADMIN_DEMO_TOKEN`。若 `DEMO_PUBLIC_MODE=true`，ngrok 網域的 WebSocket Origin 會被允許，但 POS URL 仍建議帶 `?token=<POS_DEMO_TOKEN>`。

安全原則：

- 不建議公開暴露 Admin 無 token 的網址。
- 後台敏感 API 在 `DEMO_PUBLIC_MODE=true` 時需要 `X-Admin-Token` 或 URL query `token`。
- WebSocket 在外網 demo 會檢查 token、Origin 與訊息大小。
- WebSocket query token 只是 demo 方案；反向代理與 ngrok access log 不應記錄 query string。正式版應改成短效 token 或連線後第一則 auth message。
- 目前外網 demo 建議一次只開一組客戶測試，避免 Admin `global` room 收到不同 session 事件造成混雜。
- POS 必要 API 不擋 token，避免客戶測試點餐、語音與客服流程中斷。
- 語音點餐紀錄預設不寫入 RAG，避免外網測試文字或個資污染知識庫。
- 攝影機與麥克風需由瀏覽器授權；系統只在高風險事件時擷取短片段，預設不長期保存原始影像。

三個建議測試情境：

1. **操作困惑**：執行 `tools/pos_interaction_demo_ui.py` 或開啟 `http://127.0.0.1:8000/demo-tool`，使用相同 `session_id`，按「問題 1：不會操作」。預期 POS 顯示操作提示，後台看到 `operation_confusion` 與 `show_operation_hint`。
2. **顧客詢問點餐**：在 POS 語音問答說「我要一個大麥克和一份薯條」或「我想吃雞肉，有什麼推薦？」預期 `/api/ask` 回覆只引用菜單品項，直接點餐時產生 `MCDxxx` cart actions。
3. **AI 主動推薦與 checkout 成效**：`DEMO_PUBLIC_MODE=true` 時，進入菜單頁約 8 到 12 秒會觸發一次推薦。完成 checkout 後，後台推播成效會記錄是否命中。

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
