# Smart Kiosk POS

`UI_API` 是智慧 POS 點餐與客服系統。核心原則是：POS 介面保持穩定，AI 只在需要時介入，不佔用主要點餐流程。

目前系統整合：

- FastAPI：提供 POS、後台、RAG、客服、推播與語音點餐 API。
- Emotion-LLaMA：分析顧客影像與語音情境，提供客服與推播判斷依據。
- Whisper：語音辨識與中英語言判斷。
- Ollama / Gemini API：推薦、RAG 審查與背景整理固定使用本地 Ollama；語音發問與客服回覆可在後台切換為 Gemini API。
- Ollama Embedding：RAG 向量化預設使用 `nomic-embed-text`。
- edge-tts：產生中文或英文語音回覆。
- ChromaDB：保存 Ollama 審查後的 RAG 文本。
- Interaction Event Engine：收集 POS 操作事件序列，計算互動障礙風險分數。
- Barrier State Engine：將情緒、語音、操作事件與 UI context 轉換為互動障礙狀態。
- Intervention Engine：根據互動障礙狀態產生 UI 提示、簡化介面、付款教學或店員通知。
- Customer Service State Engine：將客服語音、Emotion-LLaMA 證據與媒體訊號轉換為客服狀態、優先級與真人介入建議。

---

## 目前狀態

本次整理後，前端已從單一大型 `index.html` 拆成：

```text
index.html              # HTML 結構與 POS / 後台 DOM
static/styles.css       # 視覺樣式
static/app.js           # POS、語音、推播、後台互動邏輯
```

後端仍保留在目前穩定的三層結構：

```text
main.py                 # FastAPI routes 與流程編排
ai_services.py          # Emotion-LLaMA / Whisper / Ollama / TTS 整合
database.py             # 菜單、RAG、session、客服紀錄、推播成效資料
rag_service.py          # LangChain + Ollama 本地 RAG 與檢索策略
config.py               # .env 與 learning_data/settings.json 設定管理
```

這次沒有大幅搬動後端 API，原因是客服、RAG、推播與語音點餐都已互相串接；先拆前端可降低破壞現有流程的風險。

---

## 專案結構

```text
UI_API/
├── main.py
├── ai_services.py
├── database.py
├── config.py
├── rag_service.py
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
│   └── multimodal_routes.py
├── services/
│   ├── customer_service.py
│   ├── recommendation_service.py
│   ├── rag_review_service.py
│   ├── voice_order_service.py
│   ├── interaction_event_service.py
│   ├── barrier_state_service.py
│   ├── intervention_service.py
│   ├── customer_service_state_service.py
│   └── multimodal_evidence_service.py
├── repositories/
│   ├── log_repository.py
│   ├── menu_repository.py
│   ├── session_repository.py
│   └── interaction_event_repository.py
├── utils/
│   ├── text_utils.py
│   └── file_utils.py
├── prompts/
│   └── defaults.py
├── models/
│   └── yolo/
├── static/
│   ├── styles.css
│   ├── app.js
│   └── menu_*.png
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
├── .gitignore
├── .env
└── README.md
```

已清理內容：

- `__pycache__/`
- 非 active 的 `chroma_db_versions/*`
- 舊版 `chroma_db/`

保留內容：

- `learning_data/*.json`：正式設定、RAG、客服、推播紀錄。
- `learning_data/customer_service_media/`：後台客服可播放的顧客錄音。
- active ChromaDB 版本：由 `learning_data/rag_vector_meta.json` 指向。

---

## 執行方式

### 0. 安裝步驟

首次開發安裝：`pip install -r requirements.txt`  
正式環境安裝：`pip install -r requirements-lock.txt`（鎖定版本）

### 1. 啟動 Emotion-LLaMA

```bash
cd /home/oliver/Project_2026/Emotion-LLaMA
conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

### 2. 啟動 Ollama

```bash
ollama serve
ollama pull llama3.2
ollama pull gemma4
ollama pull nomic-embed-text
```

`AI_PROVIDER` 保持為 `ollama`，AI 推播、RAG 審查與背景整理固定使用本地 Ollama。  
`QA_AI_PROVIDER` 預設為 `ollama`，後台 AI 參數設定只會切換語音發問與客服回覆的問答來源。  
Ollama 模式下 `MODEL_NAME` 與 `ASK_MODEL_NAME` 預設為 `llama3.2`，也可切換為 `gemma4`。
`nomic-embed-text` 用於本地 RAG embedding；若不可用，系統會 fallback 到 HuggingFace embedding，避免 API 中斷。

### 2.5 啟用 Gemini API（可選）

在 `UI_API/.env` 設定 API key：

```bash
GEMINI_API_KEY=你的 Gemini API Key
```

後台「AI 參數設定」將「問答服務來源」切換為 `Gemini API` 後，下一次語音發問與客服回覆會改走 Gemini API。AI 推播、RAG 審查與背景整理仍使用本地 Ollama，避免消耗 Gemini quota。

### 3. 啟動 UI_API

```bash
cd /home/oliver/Project_2026/UI_API
conda activate emotion_ui
python main.py
```

開啟：

```text
http://127.0.0.1:8000
```

若有設定 ngrok，終端機會顯示外網網址。若固定 ngrok endpoint 已被其他程序使用，系統會略過 tunnel 並繼續啟動本機 API。

若看到 `Port 8000 已有 API 服務在執行，略過重複啟動。`，代表 UI_API 已經在跑，不需要再開第二個 `main.py`。

`/customer` 目前只是相容入口，會回到主 POS 頁；客服工作台已整合在後台「客服系統」。

---

## 使用流程

### POS 點餐

1. 進入首頁，按「開始點餐」。
2. 點選菜單卡片加入購物車。
3. 可使用「長按發問 / 語音點餐」：
   - 問推薦：例如「有什麼適合提神？」
   - 直接點餐：例如「我要兩份炸雞、一杯咖啡」
4. 語音點餐會由 Ollama 回傳 `cart_actions`，後端白名單驗證後，前端自動加入購物車。
5. 按「確認結帳」後，系統記錄推播命中與購買結果。

### POS 互動障礙偵測

前端現在會在不阻塞點餐流程的情況下，上報 POS 操作事件到 `/api/interaction_event`。
目前追蹤事件包含進入菜單頁、同頁停留超過 30 秒、返回上一頁、無效點擊、購物車修改、進入付款頁、付款嘗試、付款失敗、點擊客服、客服收音、語音點餐開始與語音點餐失敗。

`/api/interaction_event` 只做輕量記錄與風險計算。當回傳的 `risk_result.triggered=true` 時，前端才會呼叫 `/api/barrier_state`，並帶入目前 `ui_context`、最近一次語音文字、最近一次 Emotion-LLaMA 結構化結果與媒體訊號。

目前前端介入動作是最小可視化：

- `intervention.ui_patch.show_modal`：顯示簡單提示區塊。
- `intervention.staff_notify=true`：畫面提示「建議店員協助」。
- `intervention.ui_patch.disable_promotion=true`：暫停 AI 推播一段時間。

完整 UI 自動改版仍是預留 hook；目前後端會回傳 JSON 決策，前端只做初步提示與推播暫停。

後台「儀表板」新增「互動障礙與介入成效」區塊，可查看總介入次數、介入成功率、最常見 `barrier_state`、最常見 `intervention_action`、常見卡關頁面與最近 20 筆介入紀錄。這些資料可作為專利 PoC 的技術效果驗證，例如觀察卡關頁面是否集中、介入後付款 / 結帳完成率是否提升，以及是否能減少真人客服介入。

當顧客完成 `/api/checkout` 時，系統會自動尋找該 session 最近一筆尚未完成的 intervention，回寫 `checkout_success`、`payment_success`、`time_to_checkout_sec` 與 `resolved_by_checkout`。這讓「偵測 → 介入 → 成效回饋」形成閉環，後台統計可以直接反映介入後是否完成付款與結帳。

### 隱私與低算力策略

本系統採用低算力、低隱私風險、事件觸發式短片段分析架構。平時只保存 POS 操作事件、頁面狀態與互動統計，不持續保存顧客原始影像。

只有當 `INTERACTION_TRIGGER_THRESHOLD` 達到門檻時，系統才會把短時間事件脈絡、語音文字、Emotion-LLaMA 結構化分析與 UI context 組合成 `barrier_state`。短片段分析可用 `INTERACTION_PRE_EVENT_BUFFER_SEC` 與 `INTERACTION_POST_EVENT_BUFFER_SEC` 描述觸發前後的事件窗口，避免長時間連續分析。

隱私相關設定：

- `PRIVACY_SAVE_RAW_CLIP=false`：預設不保存原始情緒影像片段，只保存分析 metadata。
- `PRIVACY_RAW_CLIP_RETENTION_MINUTES=10`：若開啟原始片段保存，原始檔可按保留時間清理。
- `PRIVACY_STORE_EVENT_VECTOR_ONLY=true`：可只保留匿名化事件向量、`barrier_state` 與 `intervention_result`，降低個資與影像保存風險。

既有 emotion clip 功能仍保留；若需要後台播放原始片段，可在設定中開啟 `PRIVACY_SAVE_RAW_CLIP=true`。

### AI 推播

- 推播只顯示 Ollama 最終給客人的自然描述。
- 不顯示內部理由標籤、JSON 或除錯內容。
- A/B 模式會同時顯示 A、B 兩張推薦卡。
- 手動 RAG 規則會作為 `【RAG 全域規則】` 每次注入推播 prompt，不再只依向量相似度命中。例如「每次推播開頭都要說 Hi」會直接限制 `reason`。
- 後台「推播成效追蹤」可刪除單筆資料或清空全部資料。

### 客服

POS 左下角客服按鈕會開啟浮動客服視窗：

1. 點「開始收音」。
2. 後端用同一段 `webm` 做 Whisper 語音辨識與 Emotion-LLaMA 情緒分析。
3. 系統會把語音文字、Emotion-LLaMA 結構化情緒、YOLO 人物偵測與媒體訊號轉成 `customer_service_state`，例如付款問題、優惠券問題、操作困惑、客訴風險、趕時間或需要真人協助。
4. 若 POS 端使用 Ollama，會依語音文字、情緒、`customer_service_state`、菜單白名單與 RAG 產生客服回覆。
5. 若 `needs_human_staff=true`，客服回覆會優先簡短安撫並告知將通知店員。
6. 點擊客服視窗外部會自動關閉視窗並停止收音。

後台「客服系統」提供：

- 顧客語音文字。
- 顧客錄音播放。
- Emotion-LLaMA 情緒分析。
- `customer_service_state`、客服優先級、真人介入建議與判斷證據，並以 badge 與 details 顯示於客服紀錄卡片。
- Ollama 客服回覆。
- 真人客服輸入回覆文字。
- 「客服回覆語音」按鈕，將真人文字回覆轉成語音播放。

Emotion-LLaMA 在客服中不是單純做情緒辨識，而是提供多模態情緒與行為證據。系統會再把這些證據轉成 `customer_service_state`，用於客服優先級、真人介入判斷與回覆策略。

### RAG 文本

RAG 保存流程：

1. 菜單、手動文本、客服問答都會先送 Ollama 審查。
2. 審查後文本保存到 `learning_data/rag_docs.json`。
3. 審查紀錄保存到 `learning_data/rag_review_logs.json`。
4. ChromaDB 只使用未刪除、已審查的文本。
5. 手動 `manual` 來源會額外整理成全域規則，每次推薦與問答都會先載入，不依賴 Chroma 相似度。
6. Chroma 相似度檢索只作為補充知識，避免規則型 RAG 因 query 不相似而失效。
7. 後台可刪除 RAG 文本、單筆審查紀錄，也可一鍵清空全部 RAG 與向量庫後重建。
8. PDF 可從後台匯入，系統會依頁面與 chunk 保存來源資訊。

針對手動規則文本已加防護：

- `manual` 來源不會被改寫成假菜單 JSON。
- 若 Ollama 審查結果疑似幻覺，會保留原始規則文本。
- 中文輸出會做簡體轉繁體的基本修正。

目前 RAG 架構：

```text
menu_data/menu.json
  └─ build_menu_rag_docs()
      └─ rag_docs.json                  # 菜單基礎資料

manual / customer_service
  └─ Ollama 審查
      ├─ rag_docs.json                  # 審查後文本
      └─ rag_review_logs.json           # 審查紀錄

推薦 / 問答 / 客服
  ├─ get_global_rag_context(manual)     # 全域規則，必定注入
  └─ rag_service.retrieve(query)
      ├─ Multi-Query                    # Ollama 產生 3 個查詢
      ├─ Vector Search                  # Chroma + Ollama embedding
      ├─ BM25 Keyword Search            # 本地關鍵字檢索
      ├─ Merge + Dedup                  # 合併與去重
      ├─ Reranker                       # sentence-transformers，可 fallback
      ├─ Context Compression            # 控制 context 長度
      ├─ Answer Evaluation              # Ollama 判斷 context 是否足夠
      └─ Citation                       # file_name / page / chunk_id
```

後台「AI 設定」可開關與調整：

```yaml
rag:
  use_multi_query: true
  use_hybrid_search: true
  use_reranker: true
  use_context_compression: true
  use_answer_evaluation: true
  top_k_vector: 10
  top_k_keyword: 10
  top_k_final: 5
  context_max_chars: 2600
  embedding_provider: ollama
  embedding_model: nomic-embed-text
  reranker_model: cross-encoder/ms-marco-MiniLM-L-6-v2
```

若 `use_answer_evaluation=true` 且 Ollama 判斷檢索內容不足，RAG context 會要求回答端回覆「目前文件沒有足夠資訊」，避免亂答。

若要重置 RAG：

1. 後台「RAG 文本」按「清空 RAG」。
2. 系統會刪除 `rag_docs.json`、`rag_review_logs.json`、`rag_vector_meta.json` 與 ChromaDB 版本資料。
3. 系統自動用目前菜單重建基礎 RAG。
4. 需要的全域規則要重新新增，例如「每次推播開頭都要說 Hi」。

本次修正後，已清掉舊 RAG，並重新保留一筆全域規則：

```text
每次推播開頭都要說 Hi
```

---

## API 摘要

| API | 用途 |
| --- | --- |
| `GET /` | POS + 後台主頁 |
| `GET /customer` | 相容入口，回主頁 |
| `GET /api/menu` | 取得菜單 |
| `POST /api/menu` | 更新菜單並重建 RAG |
| `GET /api/settings` | 取得設定 |
| `POST /api/settings` | 儲存設定 |
| `POST /api/ping_state` | Emotion-LLaMA 情緒偵測 |
| `POST /api/ask` | 語音問答與語音點餐 |
| `POST /api/auto_recommend` | 自動推播推薦 |
| `POST /api/customer_service` | 客服語音分析與回覆 |
| `GET /api/customer_service_logs` | 客服紀錄 |
| `GET /api/customer_service_media/{filename}` | 播放客服錄音 |
| `POST /api/customer_service_logs/{source_id}/human_reply` | 真人客服回覆轉語音 |
| `GET /api/rag_docs` | RAG 文本與審查紀錄 |
| `POST /api/rag_docs` | 新增手動 RAG 文本 |
| `POST /api/rag_pdf` | 匯入 PDF，切 chunk 後保存到 RAG |
| `DELETE /api/rag_docs` | 清空全部 RAG、審查紀錄與向量庫 |
| `DELETE /api/rag_docs/{doc_id}` | 刪除 RAG 文本 |
| `DELETE /api/rag_review_logs/{log_index}` | 刪除審查紀錄 |
| `GET /api/logs` | 推播成效 |
| `DELETE /api/logs/{log_index}` | 刪除單筆推播成效 |
| `DELETE /api/logs` | 清空推播成效 |
| `POST /api/checkout` | 結帳並記錄成效 |
| `POST /api/interaction_event` | 記錄 POS 操作事件並計算互動障礙風險 |
| `GET /api/interaction_events/{session_id}` | 取得該 session 的互動事件 |
| `POST /api/interaction_risk` | 依最近事件重新計算互動障礙風險 |
| `POST /api/barrier_state` | 融合事件、語音、情緒與 UI context，推論互動障礙狀態與介入動作 |
| `POST /api/triggered_multimodal_analysis` | 事件觸發式多模態分析；整合短片段、Whisper、Emotion-LLaMA、POS context、barrier_state 與 intervention |
| `POST /api/intervention_result` | 回寫服務介入後的付款、結帳或店員介入結果 |
| `GET /api/intervention_logs/{session_id}` | 取得該 session 的服務介入紀錄 |
| `GET /api/intervention_stats` | 統計介入成功率、障礙狀態分布、介入動作分布與常見卡關頁面 |

---

## 專利化技術流程

本系統不是單純情緒辨識。Emotion-LLaMA 不是專利核心，而是多模態證據來源之一；核心流程是將 POS 操作行為轉換成可觸發、可執行、可回饋的服務介入策略。

流程如下：

1. POS 先收集操作事件序列，例如停留時間、付款失敗、優惠券錯誤、無效點擊、返回與購物車修改。
2. `Interaction Event Engine` 以輕量規則計算互動障礙風險分數，不在每次點擊時呼叫大型模型。
3. 只有風險分數達門檻時，才觸發多模態分析，降低持續影像分析的算力與隱私成本。
4. 多模態輸入包含 Whisper 語音文字、Emotion-LLaMA 情緒分析、媒體訊號、POS 操作事件與 UI context。
5. `Barrier State Engine` 將 `emotion_label` 與操作脈絡轉換為 `barrier_state`，例如付款卡關、操作困惑、優惠券卡關、等待不耐或需要真人協助。
6. `Intervention Engine` 將 `barrier_state` 轉換為 `intervention_action`，例如付款教學、優惠券提示、簡化介面、熱門組合推薦或店員通知。
7. `intervention_result` 會保存付款是否成功、結帳是否成功、是否通知店員與完成結帳時間，形成後續調整門檻與策略的回饋閉環。

`/api/triggered_multimodal_analysis` 是事件觸發式多模態分析入口。前端或後端可在互動障礙風險達門檻後，送入短片段與 POS context；系統會建立 `multimodal_evidence`，再推論 `barrier_state` 與 `intervention_action`。此設計避免常態保存或分析影像，可降低持續影像分析成本與隱私風險。

更完整的專利設計草稿請見 `PATENT_DESIGN.md`。

---

## 程式碼安排建議

已完成：

1. `index.html` 拆成 HTML / CSS / JS。
2. 清理舊版 ChromaDB、pycache 與不存在的獨立客服頁引用。
3. README 改成符合目前程式碼的文件。
4. `main.py` 的 API routes 拆分為 `routes/` 下獨立模組。
5. 抽離 `recommendation_service`、`customer_service`、`rag_review_service` 到 `services/`。
6. 抽離 `log_repository`、`menu_repository` 到 `repositories/`。
7. 文字工具抽離到 `utils/text_utils.py`。
8. 新增 Interaction Event / Barrier State / Intervention 三段式專利化服務介入模組。

下一階段建議：

```text
UI_API/
├── routes/
│   ├── menu_routes.py
│   ├── rag_routes.py
│   ├── recommendation_routes.py
│   ├── voice_routes.py
│   └── customer_service_routes.py
├── services/
│   ├── rag_review_service.py
│   ├── recommendation_service.py
│   ├── customer_service.py
│   ├── voice_order_service.py
│   └── language_service.py
├── repositories/
│   ├── menu_repository.py
│   ├── rag_repository.py
│   ├── log_repository.py
│   └── settings_repository.py
└── static/
    ├── styles.css
    └── app.js
```

拆分順序建議：

1. 先拆 `main.py` 裡的 RAG 審查與語音點餐解析，因為這兩段已經是純邏輯。
2. 再拆客服流程，保留 `/api/customer_service` 的 route 只負責收檔與回傳。
3. 最後拆推薦流程，讓 A/B 策略、白名單校正、快取與紀錄分開。

目前不建議一次性把後端全部搬成多檔，因為 Emotion-LLaMA、Whisper、Ollama 與 RAG 都是長耗時流程；大搬遷後若出錯，定位成本會很高。

---

## 效能策略

| 熱點 | 目前策略 |
| --- | --- |
| Emotion-LLaMA | semaphore 限制同時呼叫；POS 情緒偵測節流；客服只等待一次分析 |
| YOLO11 | 先做人物偵測；若 YOLO 偵測到人，後續情緒整理不得輸出「未偵測到顧客」 |
| 情緒訊號融合 | 依官方 `[reason]` prompt 帶入語音文字；webm 會先轉 MP4；低音量與小動作會改走保守判斷 |
| Whisper | 模型延後載入；音訊先轉 16k mono wav |
| Ollama / 可切換模型 | 預設 llama3.2，可切換 gemma4；單一 semaphore；推薦快取；A/B 可合併一次呼叫 |
| TTS | 同文字與語言使用記憶體快取 |
| RAG | ChromaDB 版本化重建；Ollama embedding；Hybrid Retrieval；Multi-Query；Reranker fallback |
| 設定 | `settings.json` mtime 快取 |
| Session | 每個 session 只保留最近 80 筆狀態 |

資源吃緊時建議：

1. 後台切到「省電」模式。
2. 關閉 A/B 推播或保留「A/B 合併成一次 Ollama 呼叫」。
3. 拉長 Emotion-LLaMA 情緒間隔。
4. 降低 Ollama 輸出上限。
5. 客服場景優先使用 Whisper + Ollama，Emotion-LLaMA 忙線時用最近一次情緒快取。

---

## Emotion-LLaMA + POS 客服的 10 個可行方案

1. 情緒分級客服路由  
   平靜問題由 Ollama 回覆，焦躁或憤怒情緒自動標示 high priority，後台提醒真人優先處理。

2. 等待不耐偵測  
   若顧客語音提到等待，且 Emotion-LLaMA 判斷不耐煩，客服回覆改用安撫與處理承諾，不再推促銷。

3. 真人客服接手摘要  
   送給真人客服的不只是逐字稿，而是「語音文字 + 情緒 + 優先級 + 建議回覆」，降低客服理解時間。

4. 服務品質儀表板  
   統計一天內高壓客服情緒、常見抱怨、等待問題比例，讓店家調整人力與出餐流程。

5. 語氣與表情不一致提醒  
   顧客文字看似普通，但影像情緒明顯焦慮時，提高客服優先級，避免漏掉隱性不滿。

6. 無障礙客服模式  
   對不方便操作螢幕的顧客，允許全語音點餐、客服協助與確認購物車。

7. 自動降噪與重問策略  
   Emotion-LLaMA / Whisper 判斷語音或影像品質差時，不讓 Ollama 硬猜，改回覆「我沒有聽清楚，請再說一次」。

8. 情緒安全回覆模板  
   對憤怒、焦躁、困惑等情緒建立固定客服回覆框架，再由 Ollama 填入菜單與現場資訊。

9. 客服訓練資料生成  
   將已審查的客服問答整理成常見情境資料，用於訓練新人或建立更穩定的客服 Prompt。

10. 即時現場協助通知  
   當 Emotion-LLaMA 偵測困惑停留太久，或客服語音出現「不會用」「找不到」「太慢」時，自動在後台置頂提醒真人介入。

---

## 常見問題

### Ollama 推薦不存在的餐點

後端會用完整菜單白名單校正 ID。若 Ollama 仍輸出不存在品項，前端不會加入購物車；推薦文字也應維持只引用真實菜單名稱。

### RAG 規則新增後推播沒有生效

舊架構只用 Chroma 相似度檢索，像「每次推播開頭都要說 Hi」這種規則不一定會被「推薦餐點」查詢命中。  
現在 `manual` RAG 會作為全域規則固定注入，因此規則型文本會穩定作用在推播 `reason` 上。

### YOLO 偵測到人，但情緒顯示未偵測到顧客

流程已改成 YOLO 優先處理人物存在判斷。若 `person_detected=true`，Emotion-LLaMA 或 Ollama 文字整理結果不得輸出「未偵測到顧客」；若無法可靠判斷情緒，會改成「無法判斷」並顯示覆寫依據。

### 低音量或動作小導致無法判斷

Emotion-LLaMA 呼叫已改用官方建議的 `[reason]` prompt 形式，並把 Whisper 語音文字放入 `The person in video says: ...`。前端錄到的 `webm` 片段會先轉成 MP4/H.264/AAC，再送到 7889 API。  
後端也會額外計算音量與動作幅度：若畫面有顧客但音量低、動作小，不會直接視為無法判斷，而是以表情、姿態、手勢與低強度狀態做保守判斷，並在情緒依據中標示。

### RAG 審查把規則改成假菜單

已針對 `source_type=manual` 加保護。手動規則會視為規則或知識，不視為菜單資料；若審查結果像假 JSON 菜單，會保留原文。

### 客服真人模式沒有聲音

真人模式不是讓 Ollama 自動回覆，而是保存顧客錄音與文字。後台輸入真人回覆後，按「客服回覆語音」會產生 TTS 並播放。

### ChromaDB readonly / lock

系統使用版本化 ChromaDB。重建時建立新資料夾，成功後才切換 `rag_vector_meta.json` 的 active dir。若仍遇到 readonly，先確認 active DB 目錄權限與是否有舊程序佔用。

### ngrok endpoint / port 8000 已佔用

`ngrok endpoint 已被其他程序使用` 不會影響本機 `http://127.0.0.1:8000` 使用。若要關閉 ngrok，可在啟動前設定：

```bash
ENABLE_NGROK=false python main.py
```

`address already in use` 代表已有 API 程序佔用 8000。新版啟動流程會先檢查 port，偵測到既有服務時直接正常退出，不再重複載入 RAG 後才失敗。
