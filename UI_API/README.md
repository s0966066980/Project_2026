# UI_API 智慧 POS 與事件觸發式客服介入系統

`UI_API` 是 Project_2026 的主要應用層，包含 FastAPI 後端、POS 前端、後台管理、語音點餐、客服、RAG、AI 推播、互動障礙偵測與 WebSocket 即時通訊。

目前系統設計重點：

> 先以 POS 操作事件判斷顧客是否可能卡關，再在必要時觸發短片段多模態分析，最後產生可執行的服務介入動作。

Emotion-LLaMA 在本系統中不是專利核心，而是多模態證據來源之一。真正的決策核心是 `risk_score → barrier_state → intervention_action → intervention_result` 的閉環。

---

## 入口與使用方式

啟動：

```bash
cd /home/oliver/Project_2026/UI_API
conda activate emotion_ui
python main.py
```

入口：

```text
客戶端 POS：http://127.0.0.1:8000
後台管理：http://127.0.0.1:8001
```

若在區網或網域環境部署：

```text
客戶端 POS：http://<host>:8000
後台管理：http://<host>:8001
```

模式隔離規則：

- `8000` 永遠是 POS 客戶端。
- `8001` 永遠是後台管理。
- 客戶端 UI 不提供後台入口。
- `8000/admin` 仍會被前端判定為 POS。
- `8001/pos` 仍會被前端判定為後台。

---

## 啟動依賴

### 1. Emotion-LLaMA

```bash
cd /home/oliver/Project_2026/Emotion-LLaMA
conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

### 2. Ollama

```bash
ollama serve
ollama pull llama3.2
ollama pull gemma4
ollama pull nomic-embed-text
```

預設模型：

- `MODEL_NAME=llama3.2`
- `ASK_MODEL_NAME=llama3.2`
- embedding 預設 `nomic-embed-text`

### 3. Python 套件

首次開發安裝：

```bash
pip install -r requirements.txt
```

正式環境安裝：

```bash
pip install -r requirements-lock.txt
```

---

## 目前整合模組

- FastAPI：API、靜態頁面、WebSocket。
- POS 前端：16:9 自助點餐 kiosk UI。
- 後台管理：設定、RAG、菜單、客服、影像片段、統計。
- Whisper：語音辨識與語言判斷。
- Ollama：預設問答、RAG 審查、推播生成。
- Gemini API：可選，只用於語音問答與客服回覆，不作為推播預設。
- Edge TTS：AI 或真人客服語音回覆。
- YOLO：人物偵測。
- Emotion-LLaMA：情緒與行為證據。
- ChromaDB：RAG 向量庫。
- LangChain + Ollama Embedding：本地 RAG。
- WebSocket realtime bus：POS、Admin、Demo、Emotion 端即時事件。
- Interaction Event Engine：POS 操作事件與風險分數。
- Barrier State Engine：互動障礙狀態推理。
- Intervention Engine：服務介入決策。
- Customer Service State Engine：客服狀態與優先級推理。

---

## 專案結構

```text
UI_API/
├── main.py
├── ai_services.py
├── database.py
├── rag_service.py
├── config.py
├── index.html
├── PATENT_DESIGN.md
├── routes/
│   ├── core_routes.py
│   ├── menu_routes.py
│   ├── rag_routes.py
│   ├── voice_routes.py
│   ├── customer_service_routes.py
│   ├── recommendation_routes.py
│   ├── emotion_routes.py
│   ├── interaction_routes.py
│   ├── multimodal_routes.py
│   ├── demo_routes.py
│   └── realtime_routes.py
├── services/
│   ├── voice_order_service.py
│   ├── recommendation_service.py
│   ├── customer_service.py
│   ├── customer_service_handler.py
│   ├── customer_service_state_service.py
│   ├── rag_review_service.py
│   ├── interaction_event_service.py
│   ├── barrier_state_service.py
│   ├── intervention_service.py
│   └── multimodal_evidence_service.py
├── repositories/
│   ├── menu_repository.py
│   ├── log_repository.py
│   ├── session_repository.py
│   ├── emotion_clip_repository.py
│   └── interaction_event_repository.py
├── realtime/
│   ├── connection_manager.py
│   └── event_bus.py
├── utils/
│   ├── text_utils.py
│   └── file_utils.py
├── prompts/
│   └── defaults.py
├── static/
│   ├── app.js
│   ├── api.js
│   ├── cart.js
│   ├── media.js
│   ├── media_buffer.js
│   ├── recommendation.js
│   ├── realtime_client.js
│   ├── styles.css
│   ├── ui.js
│   ├── mcd_start.png
│   ├── mcd_categories/
│   └── menu_images/
├── menu_data/
│   └── menu.json
├── learning_data/
│   ├── settings.json
│   ├── session_logs.json
│   ├── customer_service_logs.json
│   ├── customer_service_media/
│   ├── rag_docs.json
│   ├── rag_review_logs.json
│   ├── rag_vector_meta.json
│   ├── interaction_events.json
│   └── intervention_logs.json
├── chroma_db_versions/
├── requirements.txt
├── requirements-lock.txt
└── README.md
```

---

## 架構分層

### routes/

負責 HTTP / WebSocket endpoint，只做請求解析、檔案接收、呼叫 service、回傳 response。

主要路由：

- `core_routes.py`：首頁、設定、checkout、推播 logs。
- `menu_routes.py`：菜單讀寫。
- `voice_routes.py`：語音點餐與語音問答。
- `customer_service_routes.py`：客服請求、客服紀錄、真人回覆。
- `recommendation_routes.py`：AI 推播。
- `rag_routes.py`：RAG 文本、PDF 匯入、審查紀錄。
- `emotion_routes.py`：debug 情緒偵測、人物偵測、影像片段。
- `interaction_routes.py`：POS 事件、風險分數、互動障礙狀態、介入結果。
- `multimodal_routes.py`：事件觸發式短片段多模態分析。
- `demo_routes.py`：專利 PoC 測試情境。
- `realtime_routes.py`：WebSocket event bus。

### services/

負責業務邏輯。

- `interaction_event_service.py`：標準化 POS 操作事件、計算 `risk_score`。
- `barrier_state_service.py`：根據事件、語音、情緒與 UI context 推理 `barrier_state`。
- `intervention_service.py`：根據 `barrier_state` 產生 `intervention_action`。
- `multimodal_evidence_service.py`：整合視覺、語音、情緒與 POS 證據。
- `voice_order_service.py`：Whisper、Ollama 問答、語音點餐 cart_actions。
- `customer_service_handler.py`：客服 STT、情緒、RAG、LLM、TTS、紀錄。
- `customer_service_state_service.py`：客服狀態、優先級、真人介入建議。
- `recommendation_service.py`：AI 推播策略與白名單校正。
- `rag_review_service.py`：RAG 文本審查與清理。

### repositories/

負責 JSON / 檔案資料存取，不放商業決策。

- `menu_repository.py`：菜單。
- `log_repository.py`：推播 logs、客服 logs、RAG 審查 logs。
- `session_repository.py`：session 狀態。
- `emotion_clip_repository.py`：情緒片段 index。
- `interaction_event_repository.py`：互動事件與介入紀錄。

### realtime/

提供統一 WebSocket event bus。

```text
/ws/{client_type}/{session_id}
```

`client_type` 可為：

- `pos`
- `admin`
- `demo`
- `emotion`

主要事件：

- `interaction_intervention`
- `customer_service_request`
- `human_reply`
- `emotion_analysis_started`
- `emotion_analysis_completed`
- `settings_changed`
- `staff_notify`
- `demo_event`

---

## POS 使用流程

1. 使用者進入 `http://127.0.0.1:8000`。
2. POS 顯示 16:9 kiosk 首頁。
3. 按「開始點餐」。
4. 選擇餐點類別。
5. 點選餐點加入購物車。
6. 可繼續點餐或進入購物車。
7. 結帳頁選擇付款方式。
8. checkout 成功後：
   - 記錄推播是否命中。
   - 回寫最近一筆 open intervention 的付款 / 結帳結果。
   - 清除當前浮動提示。

POS 端同時會低成本追蹤操作事件：

- 進入菜單頁。
- 停留過久。
- 返回上一頁。
- 無效點擊。
- 購物車修改。
- 進入付款頁。
- 付款嘗試 / 付款失敗。
- 客服求助。
- 語音點餐開始 / 失敗。

---

## 後台使用流程

進入 `http://127.0.0.1:8001`。

後台包含：

- 儀表板：推播成效、互動障礙與介入成效。
- 功能模組：AI 推播、情緒泡泡、鏡頭顯示等開關。
- AI 設定：Ollama / Gemini 問答來源、RAG 參數、Emotion-LLaMA prompt。
- 影像片段：目前訂單或 session 的情緒片段紀錄。
- 菜單管理：讀寫菜單資料。
- RAG 文本：新增、審查、刪除 RAG 文本與 PDF。
- 客服系統：客服 logs、錄音播放、真人客服回覆。

後台不會自動啟動 POS 的 camera / microphone / emotion loop。只有在使用 debug recorder 或手動測試時才會請求媒體權限。

---

## 事件觸發式多模態流程

### S1. Rolling Buffer

POS 在事件觸發式多模態功能啟用時，使用 `static/media_buffer.js` 建立短時間 rolling media buffer。預設保留觸發前 5 秒，不長期保存原始影像。

## 外網客戶測試

外網 demo 使用 `DEMO_PUBLIC_MODE=true` 啟用最小保護層。建議透過反向代理或 ngrok 分別公開：

```text
POS：https://<public-pos-domain>?token=<POS_DEMO_TOKEN>
Admin：https://<public-admin-domain>?token=<ADMIN_DEMO_TOKEN>
WebSocket：wss://<domain>/ws/{client_type}/{session_id}?token=...
```

`.env` 範例：

```env
DEMO_PUBLIC_MODE=true
POS_DEMO_TOKEN=pos-demo-token
ADMIN_DEMO_TOKEN=admin-demo-token
WS_DEMO_TOKEN=optional-shared-ws-token
PUBLIC_POS_ORIGIN=https://<public-pos-domain>
PUBLIC_ADMIN_ORIGIN=https://<public-admin-domain>
ENABLE_NGROK=false
```

若只需要公開客戶端 POS，可設定 `ENABLE_NGROK=true` 與 `NGROK_AUTHTOKEN`。系統只會替 POS port 建立 tunnel；Admin 仍建議使用獨立受控網址與 `ADMIN_DEMO_TOKEN`。`DEMO_PUBLIC_MODE=true` 時，ngrok 網域的 WebSocket Origin 會被允許，但 POS URL 仍建議帶 `?token=<POS_DEMO_TOKEN>`。

專利腳本測試工具：

```text
python3 tools/pos_interaction_demo_ui.py
# 或開啟 http://127.0.0.1:8000/demo-tool
```

此工具由 `tools/pos_interaction_demo_ui.py` 內嵌 HTML 產生，只保留專利 PoC 問題：操作困惑、付款卡關、優惠券卡關、客訴風險、短片段 fallback 與 AI 主動推薦，並即時監聽 `/ws/demo/{session_id}`。

注意事項：

- Admin 不建議無 token 公開；敏感 API 會要求 `X-Admin-Token` 或 URL `token`。
- POS 必要 API 不要求 admin token，避免顧客點餐、語音、客服測試被阻斷。
- WebSocket 在 public demo 會檢查 token、Origin 與 4096 字元訊息上限。
- WebSocket query token 僅作為 demo 方案；反向代理與 ngrok access log 不應記錄 query string。正式版應改成短效 token 或連線後第一則 auth message。
- 目前外網 demo 建議一次只開一組客戶測試，避免 Admin `global` room 收到不同 session 事件造成混雜。
- 語音點餐紀錄預設不寫入 RAG，避免外網測試文字或個資污染知識庫。
- 攝影機與麥克風需授權。事件觸發式多模態只在高風險事件擷取短片段，預設不長期保存原始影像。

建議客戶測試情境：

1. **操作困惑**：開 POS `?session_id=pos_demo_001`，執行 `tools/pos_interaction_demo_ui.py` 或開 `/demo-tool`，按「問題 1：不會操作」。預期 `barrier_state=operation_confusion`，`intervention.action=show_operation_hint`。
2. **語音點餐與問答**：在 POS 說「我要一個大麥克和一份薯條」、「我想吃雞肉，有什麼推薦？」、「我不要辣，有什麼可以點？」或「最快可以做好的餐點是什麼？」。預期只回覆菜單存在品項，直接點餐時回傳 `MCDxxx` cart actions。
3. **主動推薦與 checkout 成效**：public demo 進入菜單頁後約 8 到 12 秒會先觸發一次 `auto_recommend`。推薦卡只顯示品名、價格與自然推薦語；checkout 後照常寫入推播成效。

### S2. POS 操作事件

前端把操作事件送到：

```text
POST /api/interaction_event
```

事件欄位包含：

- `session_id`
- `page_id`
- `event_type`
- `button_id`
- `dwell_time_sec`
- `back_count`
- `invalid_touch_count`
- `payment_fail_count`
- `coupon_error_count`
- `cart_edit_count`
- `idle_time_sec`
- `metadata`
- `ui_context`

### S3. Risk Score

`interaction_event_service.calculate_interaction_risk()` 根據最近事件視窗計算：

- `risk_score`
- `triggered`
- `threshold`
- `trigger_reasons`
- `event_count`
- `ui_context`

事件型態逐筆計分；累積欄位使用視窗最大值，避免重複加總導致風險膨脹。

### S4. 觸發短片段

若 `risk_result.triggered=true`，POS 會擷取觸發前 N 秒與觸發後 M 秒，送到：

```text
POST /api/triggered_multimodal_analysis
```

若 browser 沒有可用影音 stream，則 fallback 到：

```text
POST /api/barrier_state
```

### S5. 人物偵測與媒體檢查

後端先用 `ffprobe` 檢查影片是否有效，再做 YOLO 人物偵測。

若影片太小、不可讀或沒有 video stream：

- 不呼叫 Whisper。
- 不呼叫 Emotion-LLaMA。
- 回傳 `emotion_available=false`。
- 依 POS 事件 fallback 推理 `barrier_state` 與 `intervention_action`。

這避免不完整 WebM 造成 FFmpeg、Whisper 或 OpenCV crash。

### S6. Whisper + Emotion-LLaMA

影片有效時：

1. Whisper 轉語音文字。
2. `async_analyze_emotion_media_signals()` 擷取靜音、音量、動作等訊號。
3. Emotion-LLaMA 產生情緒與行為證據。
4. `customer_service.emotion_to_structured_display()` 轉成結構化情緒資料。

### S7. Multimodal Evidence

`multimodal_evidence_service.build_multimodal_evidence()` 產生：

```json
{
  "visual_evidence": {},
  "audio_evidence": {},
  "emotion_evidence": {},
  "pos_evidence": {}
}
```

### S8. Barrier State

`barrier_state_service.infer_barrier_state()` 融合：

- `emotion_structured`
- `speech_text`
- `pos_events`
- `ui_context`
- `media_signals`
- `risk_result`

輸出互動障礙狀態。

### S9. Intervention

`intervention_service.decide_intervention()` 產生：

- `action`
- `action_level`
- `staff_notify`
- `tts_text`
- `ui_patch`
- `reason`

### S10. Realtime Push

有效介入會透過 WebSocket 推送：

- POS：立即顯示協助提示。
- Admin：更新通知與統計。
- Demo：測試工具觀察事件。

### S11. Feedback

checkout 時自動更新最近 open intervention：

- `checkout_success`
- `payment_success`
- `time_to_checkout_sec`
- `resolved_by_checkout`

形成「偵測 → 介入 → 成效回饋」閉環。

---

## barrier_state 與 intervention_action

### barrier_state

| 狀態 | 意義 |
| --- | --- |
| `normal_operation` | 正常操作 |
| `menu_hesitation` | 菜單選擇猶豫 |
| `operation_confusion` | 操作困惑 |
| `payment_confusion` | 付款卡關 |
| `coupon_confusion` | 優惠券或掃碼卡關 |
| `impatience_detected` | 等待不耐 |
| `service_needed` | 需要真人協助 |
| `potential_complaint` | 疑似抱怨或客訴風險 |
| `low_confidence` | 資訊不足 |

### intervention_action

| 動作 | 意義 |
| --- | --- |
| `show_payment_tutorial` | 顯示付款教學 |
| `show_coupon_guide` | 顯示優惠券 / 掃碼教學 |
| `show_operation_hint` | 顯示操作提示 |
| `recommend_popular_combo` | 推薦熱門組合 |
| `call_staff_or_fast_mode` | 通知店員或進入快速模式 |
| `call_staff` | 通知店員 |
| `ask_clarifying_question` | 詢問釐清問題 |
| `none` | 不介入 |

---

## 客服流程

### Ollama 模式

1. POS 點客服。
2. 錄音送到 `/api/customer_service`。
3. 後端執行 Whisper、Emotion-LLaMA、客服狀態推理。
4. Ollama 產生客服回覆。
5. Edge TTS 產生語音。
6. POS 顯示並播放 AI 客服回覆。
7. 後台保存客服紀錄。

### 真人客服模式

後台把客服模式切換為 `human` 後：

1. POS 點客服並送出語音。
2. POS 立即顯示「已通知真人客服，請稍候」。
3. 後端立即透過 WebSocket 通知 Admin pending 請求。
4. 背景分析完成後更新客服紀錄。
5. 後台輸入真人回覆並按「客服回覆語音」。
6. 系統 TTS 產生語音，透過 WebSocket 推送回 POS。
7. POS 顯示「真人客服回覆」並播放語音。

真人模式下，Ollama 不會強制介入產生客服答案。

### customer_service_state

客服狀態類別：

- `normal_question`
- `operation_confusion`
- `payment_issue`
- `coupon_issue`
- `complaint_risk`
- `urgent_request`
- `angry_customer`
- `needs_human_staff`
- `low_confidence`

系統會保存：

- `customer_service_state`
- `customer_service_priority`
- `needs_human_staff`
- `service_state_evidence`
- safe allowlist 版本的 `emotion_structured`

---

## 語音點餐與語音問答

POS 語音點餐已改回按鍵觸發。顧客需長按購物車旁的麥克風按鈕開始錄音，放開後送出辨識；系統不再因
YOLO 偵測到人物而自動開始錄音。

`POST /api/ask` 流程：

1. 接收音訊。
2. Whisper 轉寫。
3. 判斷語言。
4. 若是點餐意圖，Ollama 解析餐點與數量。
5. 後端用菜單白名單校正 `cart_actions`。
6. 前端根據 `cart_actions` 加入或修改購物車。
7. 若是一般問答，回覆只顯示目前語系，不同時顯示中英文。
8. Edge TTS 產生語音回覆。

注意：

- 菜單不存在的品項不應加入購物車。
- 餐點簡稱或 STT 誤字仍會經過菜單白名單與 RAG 輔助校正。
- 推播與語音問答預設都以菜單白名單為邊界，避免幻覺餐點。

---

## AI 推播

`POST /api/auto_recommend` 負責 AI 推播。

策略：

- A 版：推薦單一餐點。
- B 版：根據歷史點餐與購物車搭配推薦組合。
- 若 Emotion-LLaMA 或互動障礙狀態可用，推播 prompt 會納入情緒與 POS context。
- 推播卡只顯示最終推薦結果，不顯示內部 reasoning、JSON 或「給客人推薦的理由」。
- 結帳後會記錄推播是否轉換。
- 後台可刪除單筆或清空全部推播成效。

---

## RAG 流程

RAG 用途：

- 菜單白名單。
- 店家規則。
- 客服知識。
- PDF 文件。
- 推播與問答限制。

目前菜單主檔為 `menu_data/menu.json`，品項圖片直接引用麥當勞台灣完整菜單頁的線上圖片 URL。菜單問答
與語音點餐以 menu JSON 的 ID、名稱、價格、分類、製作時間與 aliases 作為白名單；PDF RAG 用於補充
套餐規則、活動說明、客服話術與後台規範，不取代菜單白名單。

保存流程：

1. 新增 RAG 文本或 PDF。
2. Ollama 審查內容。
3. 保存審查後文本到 `rag_docs.json`。
4. 保存審查紀錄到 `rag_review_logs.json`。
5. 重建 ChromaDB 版本。
6. 推播、問答、客服可讀取 RAG context。

檢索流程：

```text
question
  ↓
Multi-Query
  ↓
Vector Search + BM25 Keyword Search
  ↓
Merge + Dedup
  ↓
Optional Reranker
  ↓
Context Compression
  ↓
Answer Evaluation
  ↓
Context + Citation
```

重要原則：

- `manual` 規則會當成全域規則注入，不只依相似度命中。
- 菜單資料不允許被 LLM 幻覺改寫。
- 若檢索內容不足，回答端應回覆「目前文件沒有足夠資訊」。

---

## API 摘要

### 基礎 / POS

| API | 用途 |
| --- | --- |
| `GET /` | 回傳主頁，實際模式由 port 判斷 |
| `GET /pos` | POS 相容入口 |
| `GET /admin` | 後台相容入口 |
| `GET /api/settings` | 取得設定 |
| `POST /api/settings` | 儲存設定 |
| `GET /api/menu` | 取得菜單 |
| `POST /api/menu` | 更新菜單 |
| `POST /api/checkout` | 結帳與成效回寫 |

### 語音 / 客服

| API | 用途 |
| --- | --- |
| `POST /api/ask` | 語音點餐與語音問答 |
| `POST /api/customer_service` | 客服語音分析與回覆 |
| `GET /api/customer_service_logs` | 客服紀錄 |
| `POST /api/customer_service_logs/{source_id}/human_reply` | 真人客服回覆 |

### RAG

| API | 用途 |
| --- | --- |
| `GET /api/rag_docs` | RAG 文本與審查紀錄 |
| `POST /api/rag_docs` | 新增 RAG 文本 |
| `POST /api/rag_pdf` | 匯入 PDF |
| `DELETE /api/rag_docs` | 清空 RAG |
| `DELETE /api/rag_docs/{doc_id}` | 刪除 RAG 文本 |

### 推播

| API | 用途 |
| --- | --- |
| `POST /api/auto_recommend` | AI 推播 |
| `GET /api/logs` | 推播成效 |
| `DELETE /api/logs/{log_index}` | 刪除單筆推播成效 |
| `DELETE /api/logs` | 清空推播成效 |

### 互動障礙 / 多模態 / 介入

| API | 用途 |
| --- | --- |
| `POST /api/interaction_event` | 上報 POS 操作事件並計算風險 |
| `GET /api/interaction_events/{session_id}` | 查詢 session 事件 |
| `POST /api/interaction_risk` | 重算風險 |
| `POST /api/barrier_state` | 輕量互動障礙推理 |
| `POST /api/triggered_multimodal_analysis` | 事件觸發式短片段多模態分析 |
| `POST /api/intervention_result` | 回寫介入結果 |
| `GET /api/intervention_logs/{session_id}` | 查詢介入紀錄 |
| `GET /api/intervention_stats` | 介入成效統計 |
| `POST /api/demo/trigger_scenario` | PoC 情境測試 |

### Emotion debug

| API | 用途 |
| --- | --- |
| `POST /api/ping_state` | debug 週期情緒偵測 |
| `POST /api/person_detect_frame` | 單幀人物偵測 |
| `GET /api/emotion_clips/{session_id}` | 查詢情緒片段 |
| `DELETE /api/emotion_clips/{session_id}` | 刪除情緒片段 |

---

## 後台「互動障礙與介入成效」

統計來源：

- `interaction_events.json`
- `intervention_logs.json`
- checkout 回寫結果

顯示內容：

- 總介入次數。
- 介入成功率。
- 最常見互動障礙狀態。
- 最常見服務介入動作。
- 常見卡關頁面。
- 最近介入紀錄。

用途：

- 證明系統可找到常見卡關頁面。
- 觀察介入後付款與結帳是否完成。
- 作為專利 PoC 的技術效果驗證。
- 後續可用於調整 `INTERACTION_TRIGGER_THRESHOLD` 與介入策略。

---

## 專利亮點與貢獻

### 技術問題

自助點餐機常見問題：

- 顧客不知道如何付款。
- 優惠券或 QR code 掃碼失敗。
- 菜單太多造成選擇猶豫。
- 語音或按鈕操作失敗時沒有即時協助。
- 單純情緒辨識容易受攝影機角度、低頭、口罩、表情不明顯、環境噪音影響。
- 持續影像分析會增加算力與隱私風險。

### 技術手段

本系統採用：

1. POS 操作事件序列。
2. UI context。
3. 輕量 risk score。
4. 事件觸發式短片段多模態分析。
5. YOLO 人物偵測。
6. Whisper 語音文字。
7. Emotion-LLaMA 情緒與行為證據。
8. `multimodal_evidence` 證據結構。
9. `barrier_state` 互動障礙狀態。
10. `intervention_action` 服務介入動作。
11. `intervention_result` 成效回饋。

### 技術效果

- 降低持續影像分析成本。
- 減少不必要的顧客影像保存。
- 避免 Emotion-LLaMA 單一模型誤判直接控制 POS。
- 將情緒與行為證據轉成可執行的 POS 服務介入。
- 可統計付款卡關、操作困惑、優惠券錯誤等場景的介入成效。
- 可形成偵測、介入、回饋、策略調整的閉環。

### 可主張的貢獻

- 事件觸發式多模態 POS 互動障礙偵測。
- 由 POS 操作事件風險觸發短片段分析。
- 情緒證據不直接作決策，而是轉為互動障礙狀態。
- 互動障礙狀態映射到服務介入動作。
- checkout 後自動回寫介入成效。
- 低算力與低隱私風險的 kiosk AI 架構。

更完整內容請看：

```text
PATENT_DESIGN.md
```

---

## 重要設定

設定來源：

- `.env`
- `learning_data/settings.json`
- 後台設定頁

常用設定：

```text
APP_PORT=8000
ADMIN_PORT=8001
AI_PROVIDER=ollama
QA_AI_PROVIDER=ollama
EMOTION_AI_PROVIDER=ollama
MODEL_NAME=llama3.2
ASK_MODEL_NAME=llama3.2
CUSTOMER_SERVICE_MODE=ollama
EVENT_TRIGGERED_MULTIMODAL_ENABLED=true
EMOTION_PERIODIC_ENABLED=false
INTERACTION_TRIGGER_THRESHOLD=5
INTERACTION_PRE_EVENT_BUFFER_SEC=5
INTERACTION_POST_EVENT_BUFFER_SEC=5
PRIVACY_SAVE_RAW_CLIP=false
PRIVACY_STORE_EVENT_VECTOR_ONLY=true
```

---

## 開發檢查

常用檢查：

```bash
cd /home/oliver/Project_2026
python3 -m py_compile UI_API/main.py UI_API/config.py UI_API/ai_services.py
python3 -m py_compile UI_API/routes/multimodal_routes.py
python3 -m py_compile UI_API/services/barrier_state_service.py
python3 -m py_compile UI_API/services/intervention_service.py
node --check UI_API/static/app.js
node --check UI_API/static/api.js
node --check UI_API/static/media_buffer.js
git diff --check
```

啟動後可檢查：

```bash
curl http://127.0.0.1:8000/api/settings
curl http://127.0.0.1:8001/api/settings
```

---

## 版本控制與資料保護

不應提交：

- `.env`
- 模型權重
- ChromaDB runtime 資料
- `learning_data/` runtime logs
- 顧客原始錄音 / 影像 runtime 資料
- `__pycache__/`

若需要提交範例資料，應先移除 API key、個資、錄音與影像內容。
