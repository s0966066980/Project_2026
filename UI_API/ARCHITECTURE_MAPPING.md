# 智慧自助點餐互動障礙偵測與介入系統架構對應

本文件對應 PPT「智慧自助點餐之互動障礙偵測與介入系統及其方法」流程，作為 code review 與專利 PoC 對照表。

| PPT 節點 | 對應程式檔案 | 對應 API / WebSocket | 對應資料結構 | 狀態 | 待修項目 |
| --- | --- | --- | --- | --- | --- |
| 顧客點餐機介面 | `index.html`, `static/app.js`, `static/cart.js`, `static/ui.js` | `/pos`, `/api/menu` | cart state, `menu.json` item | 已完成 | 維持現有 UI，不作大改 |
| 麥克風 → STT | `routes/voice_routes.py`, `services/voice_order_service.py`, `ai_services.py` | `POST /api/ask` | `user_text`, `detected_lang`, `raw_detected_lang` | 已完成 | STT 錯誤時需持續用實機音訊校正 |
| direct_order 點餐 | `services/query_router_service.py`, `services/voice_order_service.py`, `services/recommendation_service.py` | `POST /api/ask` | `cart_actions`, `mentioned_ids` | 已完成 | 預設不寫入 RAG |
| menu_question / ask_recommendation | `services/voice_order_service.py`, `services/recommendation_service.py` | `POST /api/ask`, `POST /api/auto_recommend` | `ai_response`, `recommendation_ids`, `audio_base64` | 已完成 | RAG 只作全域規則補充，不因 RAG 不足拒答 |
| rag_question / service_question | `services/voice_order_service.py`, `rag_service.py` | `POST /api/ask`, `/api/rag_status` | `citations`, `retrieval_evaluation`, `verification` | 已完成 | 僅此路徑執行 strict RAG 與 grounding verification |
| 點餐機操作事件 | `static/app.js`, `routes/interaction_routes.py`, `services/interaction_event_service.py`, `repositories/interaction_event_repository.py` | `POST /api/interaction_event` | `interaction_events.json`, normalized event | 已完成 | 低風險只保存事件 |
| 互動事件 → 風險分數 | `services/interaction_event_service.py` | `POST /api/interaction_event`; debug: `POST /api/debug/interaction_risk` | `risk_result`, `risk_score`, `triggered` | 已完成 | debug API 由 `ENABLE_DEBUG_ROUTES` 控制 |
| 是否達門檻 | `services/interaction_event_service.py`, `static/app.js` | `POST /api/interaction_event` | `risk_result.triggered` | 已完成 | `EVENT_TRIGGERED_MULTIMODAL_ENABLED=true` 為主流程 |
| 否：低風險事件保存 | `repositories/interaction_event_repository.py` | `POST /api/interaction_event` | `interaction_events.json` | 已完成 | 不觸發多模態與介入 |
| 是：觸發短片段 | `static/media_buffer.js`, `static/app.js`, `routes/multimodal_routes.py` | `POST /api/triggered_multimodal_analysis` | video chunk, `ui_context`, `risk_result` | 已完成 | 預設不是持續監控 |
| Whisper 語音辨識 | `ai_services.py`, `routes/multimodal_routes.py` | `POST /api/triggered_multimodal_analysis` | `speech_text` | 已完成 | 需以真實 kiosk 收音持續驗證 |
| 情緒大語言模型 | `Emotion-LLaMA/app_EmotionLlamaClient.py`, `ai_services.py` | `POST /api/triggered_multimodal_analysis`, `POST /api/customer_service` | `emotion_structured`, `emotion_risk_score` | 已完成 | Emotion-LLaMA 只作證據來源，不直接決策 |
| 多模態證據 | `services/multimodal_evidence_service.py` | `POST /api/triggered_multimodal_analysis` | `multimodal_evidence.visual/audio/emotion/pos_evidence` | 已完成 | runtime evidence 不提交 repo |
| 互動障礙狀態 | `services/barrier_state_service.py` | `POST /api/barrier_state` | `barrier_state`, `patent_category` | 已完成 | internal state 保留，另映射 PPT 三大類 |
| 介入決策引擎 | `services/intervention_pipeline_service.py`, `services/intervention_service.py` | `POST /api/barrier_state`, `POST /api/triggered_multimodal_analysis`, `/api/demo/trigger_scenario` | `intervention`, `patent_intervention_type` | 已完成 | route 不再各自重複決策 |
| 付款教學 / 操作提示 / 推薦 | `services/intervention_service.py`, `static/app.js`, `static/realtime_client.js` | WebSocket `intervention` | `ui_patch`, `tts_text` | 已完成 | 保持現有 POS 呈現 |
| 需要真人客服 | `services/customer_service_handler.py`, `services/customer_service_state_service.py` | `POST /api/customer_service`, admin WebSocket `staff_notify` | `needs_human_staff`, `priority` | 已完成 | 人工回覆由 admin route 推回 POS |
| 即時推播 | `realtime/event_bus.py`, `routes/realtime_routes.py`, `static/realtime_client.js` | `/ws/{session_id}`, `/ws/demo/{session_id}` | `intervention`, `staff_notify`, `human_reply` | 已完成 | 介入推播統一由 pipeline 發出 |
| 喇叭 → TTS | `ai_services.py`, `services/voice_order_service.py`, `services/customer_service_handler.py` | `POST /api/ask`, `POST /api/customer_service` | `audio_base64` | 已完成 | direct_order/menu_question/rag_question 都回 TTS |
| 結帳 → 成效回寫 | `routes/core_routes.py`, `repositories/interaction_event_repository.py`, `database.py` | `POST /api/checkout`, `POST /api/intervention_result` | `recommendation_result`, `intervention_result` | 已完成 | 推薦成效與介入成效分開記錄 |
| 後台統計 | `routes/interaction_routes.py`, `static/app.js` | `GET /api/intervention_stats` | `barrier_state_counts`, `patent_category_counts`, `patent_intervention_counts`, `success_rate` | 已完成 | 後續可新增 UI 欄位，但本次不大改 UI |

## PPT 三大互動障礙分類

| internal barrier_state | patent_category | patent_category_label |
| --- | --- | --- |
| `menu_hesitation` | `decision_hesitation` | 困惑、無法決定餐點 |
| `operation_confusion`, `payment_confusion`, `coupon_confusion` | `operation_failure` | 操作失敗、不會點餐 |
| `service_needed`, `potential_complaint`, `impatience_detected`, `low_confidence` | `service_or_question` | 詢問餐點、客服情況 |
| `normal_operation` | `none` | 正常操作 |

## PPT 介入動作分類

| internal action | patent_intervention_type | patent_intervention_label |
| --- | --- | --- |
| `show_payment_tutorial` | `payment_tutorial` | 付款教學 |
| `show_coupon_guide`, `show_operation_hint` | `operation_hint` | 操作提示 |
| `recommend_popular_combo` | `recommendation` | 推薦 |
| `call_staff_or_fast_mode`, `call_staff` | `human_service` | 真人客服 |
| `ask_clarifying_question` | `voice_explanation` | 語音說明 |
| `none` | `normal_interface` | 維持正常介面 |

## 單一介入資料流

`services/intervention_pipeline_service.py` 是目前統一入口：

1. 取得 recent_events。
2. 沒有 risk_result 時重新計算 risk_score。
3. 由 `barrier_state_service.infer_barrier_state()` 推論障礙狀態。
4. 由 `intervention_service.decide_intervention()` 決定介入。
5. 建立 `intervention_log`，保存 `multimodal_evidence` 與 source。
6. action 不是 `none` 時推播到 POS。
7. `staff_notify=true` 時推播到 Admin。

低風險事件只保存 `interaction_events.json`，不呼叫多模態分析，也不產生介入。
