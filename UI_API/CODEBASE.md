# UI_API Codebase 說明

每個檔案的職責、公開介面與依賴關係。

---

## 入口層

### `main.py`
FastAPI 應用程式唯一入口。

**職責：**
- 在最頂端插入 `sys.path` 讓 `backend/` 下所有模組可被直接 import（無需 `backend.X`）
- 建立 FastAPI app、設定 CORS、掛載 `frontend/` 靜態目錄至 `/static/`
- `LoopBoundSemaphore`：懶初始化的 asyncio Semaphore（跨 event loop 安全）
- `_ollama_semaphore`：全域 Ollama 並發控制（同一時間只有一個 Ollama 請求）
- `lifespan`：啟動時背景初始化 Gemini client（若啟用）
- `_route_dependencies()`：僅提供 `ollama_semaphore` 給所有路由
- `_ensure_ollama()`：啟動時自動拉 Ollama 模型（`__main__` 模式）
- 同時在 port 8000 / 8001 啟動 uvicorn（thread-based 雙 port）

**依賴：** `config`, `ai_services`, 所有 `routes/*`

---

### `config.py`
靜態設定 + 動態設定管理器。

**靜態常數（模組載入時讀取）：**
- `OLLAMA_API_URL`, `GEMINI_API_KEY`, `EMOTION_LLAMA_GRADIO_URL`
- `APP_HOST`, `APP_PORT`, `ADMIN_PORT`
- `CORS_ORIGINS`, `MENU_JSON_PATH`, `LEARNING_DATA_DIR`, `SETTINGS_JSON_PATH`
- `OLLAMA_TIMEOUT`

**動態設定系統：**
- `DEFAULT_SETTINGS`：所有動態設定的預設值
- `load_settings()`：讀取 `learning_data/settings.json`，有 mtime 快取（1 秒內不重讀）
- `save_settings(new_settings)`：寫入 settings.json，更新快取
- `get(key, default)`：外部統一讀取設定的入口
- `load_public_settings()`：只回傳 `PUBLIC_SETTINGS_KEYS` 中的設定（給 POS 前端）
- 使用 `threading.RLock()` 防止 `save_settings` → `load_settings` 的重入死鎖

**注意：** `os.makedirs(LEARNING_DATA_DIR)` 在模組載入時執行一次，不在 `load_settings()` 內重複呼叫。

---

## 後端（`backend/`）

### `backend/ai_services.py`
所有 AI 呼叫集中於此。

**Whisper（語音辨識）：**
- `init_whisper()`：懶載入 Whisper 模型
- `async_safe_transcribe_with_language(file_path)`：完整 STT 流程
  - ffprobe 探測媒體 → ffmpeg 轉 WAV → 音量/時長品質篩選 → Whisper → 清理雜訊 → 語言正規化
  - 回傳 `{text, language, raw_language}`，language 只會是 `zh` 或 `en`

**Ollama：**
- `ask_ollama(system_prompt, user_prompt, response_tag, model_name)`：本地 Ollama 主入口
- `_ask_ollama_local()`：實際 HTTP 請求，含 JSON 強制格式與自動修復
- `_repair_and_extract_json(content)`：健壯 JSON 擷取器（支援 qwen3 `<think>` block、截斷修復）

**Gemini：**
- `ask_gemini()`：Gemini API 呼叫，含 cooldown 機制（quota 錯誤後暫停）
- `init_gemini_client()`：預載 Gemini client

**TTS：**
- `generate_tts_audio_base64(text, lang)`：Edge TTS 合成，含 LRU 快取（`ENABLE_TTS_CACHE`）

**媒體：**
- `async_probe_media(file_path)`：ffprobe 探測媒體格式、音軌、影軌、時長

**依賴：** `config`, `requests`, `edge_tts`, `whisper`

---

### `backend/database.py`
連接 repositories 與 services 的輕薄資料層。

**函式：**
- `build_menu_item_text(item)`：將菜單品項格式化為 LLM 可讀文字
- `build_full_menu_context()`：組裝完整菜單白名單 context（給 Ollama prompt 用）
- `update_menu(new_menu_data)`：儲存菜單（TODO: 未來接 RAG rebuild）
- `record_final_checkout(session_id, pushed_ids, cart_ids, session_history, ai_push_cart_count, cart_sources)`：建立結帳 log entry 並寫入 session_logs

**依賴：** `repositories.menu_repository`, `repositories.log_repository`, `services.recommendation_service`

---

## 路由（`backend/routes/`）

> 所有 route 只做請求解析、呼叫 service、回傳 response，不放業務邏輯。

### `core_routes.py`
**主要 endpoints：**
- `GET /`, `GET /pos`：回傳 `frontend/pos/index.html`
- `GET /admin`：回傳 `frontend/admin/admin.html`
- `GET /api/public_settings`：回傳 POS 用公開設定
- `GET/POST /api/settings`：後台設定讀寫（需 admin token）
- `GET /api/session_stats`：推播點擊統計（total_sessions, success_rate, cart_sources）
- `DELETE /api/session_stats`：清空統計
- `GET /api/logs`：Session log 清單
- `DELETE /api/logs`, `DELETE /api/logs/{index}`：刪除 log
- `POST /api/checkout`：結帳，保存 session log，關閉 intervention

### `menu_routes.py`
- `GET /api/menu`：讀取菜單
- `POST /api/menu`：更新菜單（需 admin token）

### `voice_routes.py`
- `POST /api/ask`：語音點餐
  - 接收音訊 → 寫入 temp file → 呼叫 `voice_service.handle_voice()`

### `ai_push_routes.py`
- `POST /api/ai_push`：AI 推播
  - 接收 `session_id`, `exclude_ids` → 呼叫 `ai_push_service.generate()`

### `emotion_routes.py`
- `POST /api/emotion/analyze`：Emotion-LLaMA stub
  - 接收音訊/影片 → 呼叫 `emotion_service.analyze()`
  - 回傳 `{status: "stub", emotion_available: false, ...}`

### `interaction_routes.py`
- `POST /api/interaction_event`：保存 POS 操作事件，回傳 `{status, event}`
- `GET /api/interaction_events/{session_id}`：查詢事件（需 admin token）
- `POST /api/barrier_state`：推論障礙狀態，產生介入決策
- `POST /api/intervention_result`：更新介入結果
- `GET /api/intervention_stats`：介入統計（需 admin token）
- `DELETE /api/intervention_logs`, `DELETE /api/interaction_events`：清空紀錄

### `realtime_routes.py`
- `WS /ws/{client_type}/{session_id}`：WebSocket
  - `client_type`：`pos`, `admin`
  - POS 接收：`interaction_intervention`, `human_reply`, `settings_changed`
  - Admin 接收：`staff_notify`, `settings_changed`

### `demo_routes.py`
- `POST /api/demo/trigger_scenario`：觸發測試情境
  - 支援情境：`operation_difficulty`, `menu_hesitation`, `payment_problem`, `human_service`, `low_risk`
  - 會儲存 mock 事件，執行完整 intervention pipeline，回傳結果
  - `LEGACY_SCENARIO_ALIASES`：舊情境 ID 映射

### `debug_routes.py`（ENABLE_DEBUG_ROUTES=true 才啟用）
- `GET /api/debug/intervention_logs/{session_id}`：查詢介入紀錄

---

## 服務（`backend/services/`）

### `voice_service.py`
語音點餐完整流程（STT → Ollama → TTS）。

**`handle_voice(session_id, audio_path, ollama_semaphore, multi_lang)`：**
1. `ai_services.async_safe_transcribe_with_language()` → `user_text`, `detected_lang`
2. `database.build_full_menu_context()` → 菜單白名單 context
3. 依 `detected_lang` 選 system prompt（`VOICE_ASSIST_SYSTEM_PROMPT` 或 `VOICE_ASSIST_SYSTEM_PROMPT_EN`）
4. `# TODO: inject RAG context here`（RAG 插槽）
5. `ai_services.ask_ollama()` → `ai_response`, `cart_actions`
6. `recommendation_service.coerce_cart_actions()` → 白名單校正
7. `session_repository.record_session_state()` → 保存對話
8. `ai_services.generate_tts_audio_base64()` → 語音回傳

**回傳：** `{status, user_text, ai_response, audio_base64, cart_actions, detected_lang}`

### `ai_push_service.py`
AI 推播邏輯。

**`generate(session_id, ollama_semaphore, exclude_ids)`：**
1. 從菜單挑優先分類（超值全餐、極選系列、點心、飲料）
2. 呼叫 Ollama 選 1 品 + 促購短句（18~34 字）
3. 若 Ollama 失敗，本地隨機備選

**回傳：** `{status, recommendation_id, push_text}`

### `emotion_service.py`
Emotion-LLaMA 事件驅動分析服務。

**`is_enabled()`：**
- 讀取 `config.get("EMOTION_LLAMA_ENABLED", False)`

**`analyze(session_id, media_path)`（向下相容）：**
- 固定回傳 stub 格式（`emotion_available: False`），供 `POST /api/emotion/analyze` 使用

**`analyze_event(session_id, media_path, event_type)`（主入口）：**
1. `is_enabled()` 檢查，未啟用回傳 `{status: "disabled"}`
2. 讀取 prompt template（`EMOTION_LLAMA_PROMPT`）
3. `_call_gradio(media_path, question, skip_quality_check)` → Gradio HTTP API
4. 解析回傳 JSON（支援 `[EMOTION_LLAMA_SKIP]` / `[EMOTION_LLAMA_ERROR]` 前綴）
5. `emotion_log_repository.append_log(entry)` 寫入紀錄
6. 若有有效情緒結果：更新 `_voice_cache[session_id]`；若 `EMOTION_LLAMA_AFFECT_BARRIER` 啟用，以 `asyncio.create_task` 觸發 barrier pipeline

**語音快取：**
- `get_voice_emotion_cache(session_id)` → 取得快取，供 `voice_service` 注入 prompt
- `clear_voice_emotion_cache(session_id)` → 清除快取

**`EVENT_TYPE_LABELS`：** 事件類型中文對照（`"tutorial_popup"` → `"如何點餐彈跳視窗"`）

### `barrier_state_service.py`
POS 事件 + 語音 → 互動障礙狀態推論。

**`infer_barrier_state(speech_text, pos_events, ui_context)`：**
- 讀取事件計數：`payment_fail_count`, `coupon_error_count`, `category_switch_count`, `cart_remove_count`, `dwell_time_sec`
- 依優先順序 elif 鏈判斷：
  1. 語音抱怨 → `potential_complaint`
  2. payment_page + fail_count → `payment_confusion`
  3. 語音付款問題 → `payment_confusion`
  4. coupon_page + error_count → `coupon_confusion`
  5. 語音猶豫 → `menu_hesitation`（不需在菜單頁）
  6. menu_page + 計數/逾時 → `menu_hesitation`
  7. 語音不會操作 → `operation_confusion`
  8. 語音急躁 → `impatience_detected`
  9. 無事件且無語音 → `low_confidence`
  10. 其他 → `normal_operation`
- 計算 confidence/severity（基於 evidence 數量）
- 回傳完整 barrier_result dict（含 category/patent 分類）

### `intervention_service.py`
barrier_state → intervention_action 決策。

**`decide_intervention(barrier_result, ui_context)`：**
- 查 `_STATE_PRESENTATION` 取對應 tts_text, ui_patch, staff_notify
- 嚴重度高時升級 action_level 或啟用 staff_notify
- 回傳 `{action, action_level, staff_notify, tts_text, ui_patch, reason}`

**`build_intervention_log(session_id, barrier_result, intervention, ui_context)`：**
- 建立 log payload，初始 `result: {}`

### `intervention_pipeline_service.py`
完整介入流程統一入口。

**`run_intervention_pipeline(session_id, ui_context, recent_events, speech_text, scenario_id, source, publish)`：**
1. 取最近事件（無則從 DB 讀）
2. `barrier_state_service.infer_barrier_state()`
3. `scenario_service` 附加 scenario_id/label
4. `intervention_service.decide_intervention()`
5. `should_log`：barrier_state ≠ normal_operation → 寫入 intervention_log
6. `publish=True` 且 `action ≠ none` → `event_bus.publish_intervention()`
7. `staff_notify` → `event_bus.publish_to_admin("staff_notify", ...)`

### `interaction_event_service.py`
POS 事件標準化。

**`normalize_interaction_event(payload)`：**
- 將 HTTP payload 正規化為標準 event dict
- `NUMERIC_FIELDS`：保留的數值欄位（`dwell_time_sec`, `back_count`, `payment_fail_count` 等）

### `scenario_service.py`
情境 ID 正規化與 metadata 附加。

**主要資料：**
- `SCENARIO_DEFINITIONS`：三大情境（operation_difficulty, menu_hesitation, payment_problem）
- `LEGACY_SCENARIO_ALIASES`：舊 ID 映射
- `_BARRIER_TO_SCENARIO`：barrier_state → scenario_id 對照

**主要函式：**
- `normalize_scenario_id(raw)` → 標準 scenario_id
- `infer_scenario_from_barrier_state(barrier_state)` → scenario_id
- `attach_scenario_metadata(payload, scenario_id)` → 附加 scenario_id/label（原地修改）
- `get_scenario_definition(scenario_id)` → 情境定義 dict

### `recommendation_service.py`
語音點餐白名單校正與工具函式。

**主要函式：**
- `clean_menu_id(raw_id, menu_ids)` → 模糊比對回標準 MCDxxx ID
- `coerce_cart_actions(raw_actions, user_text, menu_items)` → 校正 LLM cart_actions，fallback 到文字比對
- `normalize_order_text(text)` → 繁體 + 常見錯字替換 + 正規化
- `menu_aliases(item)` → 品項所有別名（含後綴、類別別名）
- `fallback_cart_actions_from_text(user_text, menu_items)` → 純文字比對加入購物車
- `build_checkout_log_entry(...)` → 建立 session log entry dict
- `parse_quantity(raw)` → 數量解析（支援中文數字）

---

## 資料存取（`backend/repositories/`）

### `emotion_log_repository.py`
讀寫 `learning_data/emotion_intervention_logs.json`。

- `append_log(entry)` → 原子 append 分析紀錄
- `get_logs(limit=200)` → 取最新 N 筆（由新到舊由外部 reverse）
- `clear_logs()` → 清空並回傳清除筆數
- 使用 `threading.Lock()` 確保並發安全

---

### `interaction_event_repository.py`
最複雜的 repository，含完整讀寫機制。

- 讀寫 `learning_data/interaction_events.json`（事件）和 `intervention_logs.json`（介入紀錄）
- 使用 per-path `threading.Lock()` + `{path}.{pid}.{tid}.tmp` 確保並發安全
- `get_recent_session_events(session_id, window_sec)` → 過濾近期事件
- `append_interaction_event(event)` → 原子寫入事件
- `append_intervention_log(log)` → 原子寫入介入紀錄，附加 UUID intervention_id
- `find_latest_open_intervention(session_id)` → 找最新未關閉介入
- `update_intervention_result(intervention_id, result)` → 回寫介入結果

### `log_repository.py`
讀寫 `learning_data/session_logs.json`。

- `get_session_logs()` / `save_session_logs(logs)` — 含 mtime 快取
- `append_session_log(log_entry)` → 原子 append
- `delete_session_log(log_index)` → 刪除單筆
- `clear_session_logs()` → 清空
- 使用 `{path}.{pid}.{tid}.tmp` 防並發覆蓋

### `menu_repository.py`
讀寫 `menu_data/menu.json`，含 mtime 快取。

- `get_menu()` → 回傳菜單（快取命中則不重讀）
- `save_menu(menu_data)` → 原子寫入，更新快取

### `session_repository.py`
記憶體內 session 狀態（page reload 即清空）。

- `record_session_state(session_id, emotion, user_speech, ai_response, language)` → 追加至 dict
- `get_session_history(session_id)` → 取語音對話歷史（給 LLM context）
- `archive_session(session_id)` → 結帳後清除

---

## 即時通訊（`backend/realtime/`）

### `connection_manager.py`
- WebSocket 連線 pool：`Dict[str, List[WebSocket]]`
- `connect(ws, client_type, session_id)` → 加入 pool
- `disconnect(ws, client_type, session_id)` → 移出 pool
- `broadcast(client_type, session_id, message)` → 推送給特定 client

### `event_bus.py`
- `publish_intervention(session_id, pipeline_result)` → 推送介入事件給 POS
- `publish_to_admin(event_type, payload)` → 推送 staff_notify、settings_changed 給 Admin
- `publish_event(event)` → 通用推送（settings_changed 等）

---

## 工具（`backend/utils/`）

### `text_utils.py`
- `to_traditional_lite(text)` → 簡繁轉換
- `has_cjk(text)` / `latin_noise_count(text)` → 語言特徵偵測
- `normalize_emotion_label(text)` → 情緒標籤正規化

### `auth_utils.py`
- `require_admin_token(request)` → 驗證 `X-Admin-Token` header 或 `token` query param

### `file_utils.py`
- `write_binary_file(path, data)` → 同步二進位寫入（供 asyncio.to_thread 使用）

---

## 前端詳細說明

### `frontend/pos/app.js`（主控制器，約 2500 行）

**主要功能區塊：**

| 功能 | 說明 |
|------|------|
| 菜單渲染 | `renderMenu()`, `renderKioskCategories()`, kiosk 分組瀏覽 |
| 購物車 | `trackedAddToCart()`, `trackedUpdateCartQty()`, `trackedDeleteCartItem()` — 含 `sessionCartSources` 來源追蹤 |
| AI 推播欄 | `aiPush` 物件：`start/stop/hide/scheduleAfterCartClose`，15 秒輪替 |
| 猶豫彈跳視窗 | `choiceHesitationTimer`：購物車空 60 秒後觸發，`restartChoiceHesitationTimer()` |
| 語音點餐 | `startAskRecording()` → 錄音 → `api.ask()` → TTS 播放 + cart_actions 加入 |
| 互動追蹤 | `trackInteractionEvent()` → `reportInteractionEvent()` → `POST /api/interaction_event` |
| WebSocket | `startPosRealtime()` — 接收 `interaction_intervention`, `human_reply`, `settings_changed` |
| 結帳 | `writeCheckoutLog()` → `POST /api/checkout`（含 `sessionCartSources`, `sessionAiPushCartCount`） |
| Emotion 觸發 | `_triggerEmotionCapture(eventType)` — 非阻擋；呼叫 `capturePreEventClip()` 後 fire-and-forget `api.analyzeEmotionEvent()` |

**關鍵 session 狀態：**
- `sessionId`：per-page-load unique ID
- `sessionPushedIds`：AI 推播過的品項 Set
- `sessionAiPushCartCount`：AI 推播/猶豫視窗加入次數
- `sessionCartSources`：`[{id, source}]` — 每筆加入的來源追蹤

**加入方式（source）：**
- `ai_push`：AI 推播欄按下
- `choice_hesitation`：猶豫彈跳視窗
- `voice_assist`：語音點餐
- `manual`（預設）：手動點選菜單

**Rolling Buffer（Emotion-LLaMA 事件截片）：**
- `startRollingBuffer(stream, clipSec)` → 啟動 500ms chunk MediaRecorder，維持固定長度環形 buffer
- `stopRollingBuffer()` → 停止並清空 buffer
- `capturePreEventClip()` → 快照目前 buffer + 觸發 `requestData()`，回傳 `Blob | null`；含 100ms 保底 timeout 防 callback 未觸發

### `frontend/pos/cart.js`
- `createCartManager({ui, escapeHTML, findMenuItems, onCartChange, t})` → 工廠函式
- 內部 `cart` 物件：`{id: {item, quantity}}`
- `addToCart(item)`, `updateCartQty(id, delta)`, `deleteCartItem(id)`, `clearCart()`
- `applyCartActions(actions)` → 語音點餐批次加入（bypass trackedAddToCart）
- `renderCart()` → 動態產生購物車 HTML（含 `onclick="updateCartQty"` inline handler）

### `frontend/admin/admin.js`
- `loadStats()` → `GET /api/session_stats` → 更新統計卡、donut chart
- `renderTop3(sessions)` → 統計所有 session `final_cart_ids` 出現頻率，顯示 TOP3
- `renderTable(sessions)` → 顯示 session 清單，含「加入方式」欄（從 `cart_sources` 聚合）
- `SOURCE_LABELS`：`{ai_push: 'AI推播', choice_hesitation: '猶豫視窗', voice_assist: '語音點餐', manual: '手動'}`

### `frontend/shared/api.js`
所有後端 API 呼叫的封裝模組（ES modules export）。

主要 export：
- `getPublicSettings()`, `getSettings()`, `saveSettings()`
- `getMenu()`, `saveMenu()`
- `ask(formData)` → 語音點餐
- `aiPush(formData)` → AI 推播
- `checkout(formData, signal)` → 結帳
- `reportInteractionEvent(payload)` → POS 事件
- `getLogs()`, `clearLogs()`, `deleteLog(index)`
- `getInterventionStats()`
- `analyzeEmotionEvent(sessionId, eventType, mediaBlob)` → `POST /api/emotion/analyze_event`
- `getEmotionInterventionLogs(limit)` → `GET /api/emotion/intervention_logs`
- `getOllamaModels()` 等管理功能

---

## 資料流圖

### 語音點餐流程

```
[前端] 麥克風錄音（media_buffer.js）
  → POST /api/ask（音訊 webm）
    → voice_service.handle_voice()
      → ai_services.async_safe_transcribe_with_language()  [Whisper STT]
      → database.build_full_menu_context()                  [菜單 context]
      → ai_services.ask_ollama()                            [Ollama LLM]
      → recommendation_service.coerce_cart_actions()        [白名單校正]
      → ai_services.generate_tts_audio_base64()             [Edge TTS]
  → {user_text, ai_response, audio_base64, cart_actions}
[前端] 播放 TTS + 執行 cart_actions
```

### 互動障礙介入流程

```
[前端] POS 事件（點擊、停留、付款失敗等）
  → POST /api/interaction_event
    → interaction_event_service.normalize_interaction_event()
    → interaction_event_repository.append_interaction_event()
  → {status, event}

[前端] 語音輸入 or 管理端觸發
  → POST /api/barrier_state
    → intervention_pipeline_service.run_intervention_pipeline()
      → barrier_state_service.infer_barrier_state()   [POS 事件 + 語音 → barrier_state]
      → scenario_service.attach_scenario_metadata()   [情境 label]
      → intervention_service.decide_intervention()    [barrier_state → action]
      → interaction_event_repository.append_intervention_log()
      → event_bus.publish_intervention()              [推送 WS]
      → event_bus.publish_to_admin("staff_notify")    [若需要]

[前端] WebSocket 接收 intervention
  → applyIntervention()                               [顯示介入卡]

[前端] 結帳
  → POST /api/checkout
    → _mark_latest_intervention_checkout()            [關閉 intervention]
    → database.record_final_checkout()                [session log]
  → POST /api/intervention_result                     [回寫結果]
```

### AI 推播流程

```
[前端] aiPush.start() / _fetch()
  → POST /api/ai_push
    → ai_push_service.generate()
      → Ollama 選品 + 促購短句
      → 回傳 {recommendation_id, push_text}
[前端] 底部欄顯示推薦，顧客點選 → trackedAddToCart(source='ai_push')
```

---

## 重要設計決策

1. **`sys.path` 橋接**：`main.py` 執行時 `backend/` 加入 `sys.path[0]`，所有 `backend/` 下的 import 無需前綴
2. **`menu_data/` 保持根目錄**：`config.py` 使用 CWD 相對路徑 `./menu_data/menu.json`
3. **`cart_sources` 在前端追蹤**：`sessionCartSources` 在每次 `trackedAddToCart`/`applyCartActions` 時記錄，結帳時傳給後端
4. **Emotion-LLaMA 事件驅動**：`emotion_service.py` 實作 `analyze_event()`，事件觸發時截片送 Gradio；`analyze()` 保留 stub 格式維持向下相容。`EMOTION_LLAMA_ENABLED`（Public Settings）控制是否啟用，預設 `false`
5. **RAG 插槽**：`voice_service.py` prompt 組裝前有 `# TODO: inject RAG context here`，未來接入時只改這一處
6. **Barrier state 不依賴 risk score**：直接用 POS 事件計數（`payment_fail_count`、`category_switch_count` 等）+ 語音關鍵字判斷，無需計算風險分數
