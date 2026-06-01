# 架構對應說明 — 互動障礙偵測與介入系統

本文件對應專利流程「智慧自助點餐之互動障礙偵測與介入系統」，作為 code 與概念 PoC 的對照表。

---

## 核心流程對應

| 功能節點 | 程式檔案 | API / WebSocket | 資料結構 |
|----------|----------|-----------------|----------|
| POS kiosk 介面 | `frontend/pos/index.html`, `app.js`, `cart.js` | `GET /pos`, `GET /api/menu` | `cart state`, `menu.json` |
| 語音點餐（STT） | `backend/services/voice_service.py`, `ai_services.py` | `POST /api/ask` | `user_text`, `detected_lang` |
| 語音點餐（LLM + TTS） | `backend/services/voice_service.py`, `ai_services.py` | `POST /api/ask` | `ai_response`, `cart_actions`, `audio_base64` |
| POS 操作事件記錄 | `frontend/pos/app.js`, `backend/routes/interaction_routes.py`, `backend/services/interaction_event_service.py` | `POST /api/interaction_event` | `interaction_events.json`, normalized event |
| 事件計數統計 | `backend/services/barrier_state_service.py` | `POST /api/barrier_state` | `payment_fail_count`, `category_switch_count`, `cart_remove_count` 等 |
| 互動障礙狀態推論 | `backend/services/barrier_state_service.py` | `POST /api/barrier_state` | `barrier_state`, `evidence`, `confidence`, `severity` |
| 介入決策引擎 | `backend/services/intervention_service.py`, `intervention_pipeline_service.py` | `POST /api/barrier_state`, `/api/demo/trigger_scenario` | `intervention_action`, `patent_intervention_type`, `tts_text`, `ui_patch` |
| 付款教學 / 操作提示 / 推薦 | `backend/services/intervention_service.py`, `frontend/pos/app.js` | WebSocket `interaction_intervention` | `ui_patch`, `show_modal` |
| 真人客服通知 | `backend/realtime/event_bus.py` | Admin WebSocket `staff_notify` | `needs_human_staff`, `reason` |
| AI 推播 | `backend/services/ai_push_service.py`, `frontend/pos/app.js` | `POST /api/ai_push` | `recommendation_id`, `push_text` |
| 猶豫彈跳視窗 | `frontend/pos/app.js` | 前端本地邏輯（60 秒 idle timer） | `choiceHesitationTimer`, `sessionCartSources` |
| 即時推播 | `backend/realtime/event_bus.py`, `backend/routes/realtime_routes.py` | `WS /ws/pos/{session_id}`, `WS /ws/admin/global` | `intervention`, `staff_notify`, `settings_changed` |
| TTS 語音回覆 | `backend/ai_services.py` | `POST /api/ask`（回傳） | `audio_base64` |
| 結帳 → 成效回寫 | `backend/routes/core_routes.py`, `backend/repositories/interaction_event_repository.py` | `POST /api/checkout`, `POST /api/intervention_result` | `session_logs.json`, `intervention_logs.json` |
| 後台統計 | `frontend/admin/admin.js`, `backend/routes/interaction_routes.py`, `backend/routes/core_routes.py` | `GET /api/intervention_stats`, `GET /api/session_stats` | `barrier_state_counts`, `success_rate`, `cart_sources` |
| Emotion-LLaMA 事件分析 | `backend/services/emotion_service.py`, `backend/routes/emotion_routes.py`, `backend/repositories/emotion_log_repository.py` | `POST /api/emotion/analyze_event`, `GET/DELETE /api/emotion/intervention_logs` | 事件觸發截片 → Gradio API（port 7889）→ `emotion_intervention_logs.json`；可選注入語音 prompt 或觸發 barrier pipeline |
| Emotion-LLaMA（通用，向下相容） | `backend/services/emotion_service.py` | `POST /api/emotion/analyze` | stub 格式，`emotion_available: false` |

---

## 三大互動障礙分類

| barrier_state | patent_category | patent_category_label |
|---|---|---|
| `menu_hesitation` | `decision_hesitation` | 困惑、無法決定餐點 |
| `operation_confusion`, `payment_confusion`, `coupon_confusion` | `operation_failure` | 操作失敗、不會點餐 |
| `service_needed`, `potential_complaint`, `impatience_detected`, `low_confidence` | `service_or_question` | 詢問餐點、客服情況 |
| `normal_operation` | `none` | 正常操作 |

---

## 介入動作分類

| action | patent_intervention_type | patent_intervention_label |
|---|---|---|
| `show_payment_tutorial` | `payment_tutorial` | 付款教學 |
| `show_coupon_guide`, `show_operation_hint` | `operation_hint` | 操作提示 |
| `recommend_popular_combo` | `recommendation` | 推薦 |
| `call_staff_or_fast_mode`, `call_staff` | `human_service` | 真人客服 |
| `ask_clarifying_question` | `voice_explanation` | 語音說明 |
| `none` | `normal_interface` | 維持正常介面 |

---

## 介入 Pipeline 資料流

`backend/services/intervention_pipeline_service.py` 為統一入口：

```
run_intervention_pipeline(session_id, ui_context, recent_events, speech_text, ...)
  │
  ├─ barrier_state_service.infer_barrier_state()
  │     → 事件計數 (payment_fail, category_switch, dwell_time, ...)
  │     → 語音關鍵字分析
  │     → 輸出 barrier_state, evidence, confidence, severity
  │
  ├─ scenario_service.attach_scenario_metadata()
  │     → 附加 scenario_id, scenario_label
  │
  ├─ intervention_service.decide_intervention()
  │     → 查 _STATE_PRESENTATION
  │     → 輸出 action, action_level, tts_text, ui_patch, staff_notify
  │
  ├─ interaction_event_repository.append_intervention_log()  [barrier_state ≠ normal]
  │
  ├─ event_bus.publish_intervention()  [action ≠ none]
  │     → WS 推送 POS
  │
  └─ event_bus.publish_to_admin("staff_notify")  [staff_notify = true]
        → WS 推送 Admin
```

---

## 加入方式追蹤（cart_sources）

| source | 觸發路徑 | 統計欄位 |
|--------|----------|----------|
| `ai_push` | AI 推播欄「加入購物車」 | `sessionAiPushCartCount` |
| `choice_hesitation` | 猶豫彈跳視窗「我要這個」 | `sessionAiPushCartCount` |
| `voice_assist` | 語音點餐 `applyCartActions` | - |
| `manual` | 手動點選菜單 | - |

結帳時 `sessionCartSources = [{id, source}, ...]` 傳給後端，存入 `session_logs.json`，後台「加入方式」欄顯示。

---

## Demo 情境（`POST /api/demo/trigger_scenario`）

| scenario | 說明 | 對應 barrier_state |
|----------|------|-------------------|
| `operation_difficulty` | 無效點擊 + 停留長 + 語音「不會操作」 | `operation_confusion` |
| `menu_hesitation` | 分類切換多次 + 停留長 + 語音「不知道吃什麼」 | `menu_hesitation` |
| `payment_problem` | 付款失敗 + 付款頁停留 | `payment_confusion` |
| `human_service` | 付款失敗 + 抱怨語音 | `potential_complaint` / `service_needed` |
| `low_risk` | 正常瀏覽 | `normal_operation` |
