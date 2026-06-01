# 事件觸發式多模態 POS 顧客互動障礙偵測與自適應服務介入系統

本文件是技術設計與概念版專利請求項草稿，不是法律最終版。實際申請前仍需由專利代理人依各國法規整理。

> **實作現況說明（2026-06）**
> 本文件描述的是完整專利概念架構。目前原型系統的實作狀態：
> - **已實作**：POS 事件記錄、barrier_state 推論（基於事件計數 + 語音）、intervention_action 決策、WebSocket 推播、語音點餐（STT→LLM→TTS）、AI 推播、猶豫彈跳視窗
> - **已實作（Emotion-LLaMA 事件驅動）**：前端 rolling buffer 截片 → `POST /api/emotion/analyze_event` → Gradio API（port 7889）→ log 寫入；可選注入語音 prompt 或觸發 barrier pipeline
> - **尚未實作**：事件觸發式 risk_score 門檻機制（已移除，改由語音輸入或管理端手動觸發 barrier_state 分析）
> - **可選模組**：RAG（fastembed，無文件時自動跳過）
> 
> 詳細現況架構請參考 `CODEBASE.md` 與 `ARCHITECTURE_MAPPING.md`。

## 1. 技術問題

自助點餐機通常只能被動接收顧客點擊、付款或取消操作，無法即時判斷顧客是否在付款、優惠券、菜單選擇或操作流程中卡關。當顧客因不熟悉介面、付款失敗、優惠券掃碼錯誤或長時間停留而產生障礙時，系統往往只能等顧客主動求助，導致排隊、抱怨或放棄購買。

單純使用人臉情緒辨識也存在限制。顧客可能低頭看螢幕、戴口罩、站在攝影機角度之外，或因表情強度低而不容易被穩定辨識；環境噪音也會干擾語音與情緒判斷。若系統持續分析所有影像，還會增加算力負擔、裝置溫度、延遲與隱私風險。

因此，本系統的核心不是單純判斷 `emotion_label`，而是根據 POS 操作事件、UI 狀態、語音文字、情緒分析與媒體訊號，判斷顧客是否出現「互動障礙」，並在達到門檻時觸發 UI 或客服介入。

## 2. 技術手段

系統先收集 POS 操作事件序列，例如目前頁面、按鈕、停留時間、返回次數、付款失敗次數、無效點擊次數、優惠券錯誤次數、購物車修改次數與閒置時間。

系統根據事件序列計算互動障礙風險分數。初版規則包含：

- 付款失敗增加較高風險。
- 優惠券或掃碼錯誤增加中度風險。
- 多次返回、長時間停留、無效觸控與閒置增加補充風險。
- 在付款頁長時間停留時提高風險。
- 在結帳頁返回時提高風險。

只有當風險分數達到門檻時，才觸發多模態分析。多模態資料包含：

- 影像 / video。
- 語音 / audio。
- Whisper 語音文字。
- Emotion-LLaMA 情緒分析。
- POS 操作事件序列。
- UI context，例如目前頁面、付款頁、菜單頁、優惠券頁或結帳頁。
- 媒體訊號，例如音量、靜音狀態、動作幅度與人物偵測結果。

多模態推理結果不是單純情緒標籤，而是 `barrier_state`，例如付款卡關、優惠券卡關、操作困惑、菜單猶豫、等待不耐、需要真人協助或資訊不足。

Emotion-LLaMA 在本系統中不是專利核心，而是證據產生器之一。其輸出會與 POS 操作事件、UI context、Whisper 語音文字、人物偵測與媒體訊號整合成 `multimodal_evidence`，再由 Barrier State Engine 轉換成互動障礙狀態。Emotion-LLaMA 不直接決定服務介入動作，介入動作由事件風險與障礙狀態共同決定。

系統再根據 `barrier_state` 產生 `intervention_action`，例如：

- 顯示付款教學。
- 顯示優惠券使用提示。
- 切換簡化操作模式。
- 推薦熱門組合。
- 暫停促銷推播。
- 通知真人客服。
- 以 TTS 詢問顧客需要哪一類協助。

介入後，系統保存 `intervention_feedback`，例如是否付款成功、是否結帳成功、是否通知店員、介入後多久完成結帳。後續可根據回饋調整門檻或介入策略。

## 3. 技術效果

- 降低持續影像分析的運算成本：先以 POS 事件做輕量風險評估，只在必要時觸發多模態分析。
- 減少不必要的顧客影像保存：未達風險門檻時不需要保存或分析影像片段。
- 在顧客卡關時即時提供 UI 或真人客服協助：系統可主動顯示付款、優惠券或操作提示。
- 將情緒辨識轉成具體 POS 控制動作：Emotion-LLaMA 只作為多模態訊號之一，最終輸出是可執行的服務介入。
- 透過介入成效回饋改善後續策略：系統可追蹤介入後是否縮短結帳時間、降低付款失敗或減少客服等待。

## 4. 系統架構圖

```text
POS 操作事件
  ├─ page_id / event_type / button_id
  ├─ dwell_time_sec / idle_time_sec
  ├─ back_count / invalid_touch_count
  ├─ payment_fail_count / coupon_error_count
  └─ cart_edit_count
        │
        ▼
互動障礙風險分數 risk_score
        │
        ├─ 未達門檻 → 正常 POS 流程，避免重型分析
        │
        ▼
達門檻 triggered=true
        │
        ▼
事件觸發式多模態融合
  ├─ video / audio
  ├─ Whisper 語音文字
  ├─ Emotion-LLaMA 情緒分析
  ├─ POS 操作事件序列
  ├─ UI context
  └─ media_signals
        │
        ▼
barrier_state
  ├─ payment_confusion
  ├─ coupon_confusion
  ├─ operation_confusion
  ├─ menu_hesitation
  ├─ impatience_detected
  ├─ service_needed
  └─ low_confidence
        │
        ▼
intervention_action
  ├─ show_payment_tutorial
  ├─ show_coupon_guide
  ├─ show_operation_hint
  ├─ recommend_popular_combo
  ├─ call_staff_or_fast_mode
  └─ call_staff
        │
        ▼
intervention_feedback
  ├─ payment_success
  ├─ checkout_success
  ├─ staff_called
  └─ time_to_checkout_sec
        │
        ▼
門檻與策略調整
```

## 5. 概念版專利請求項草稿

1. 一種事件觸發式多模態 POS 顧客互動障礙偵測與自適應服務介入方法，包含：取得一自助點餐機於一顧客工作階段中的操作事件序列，該操作事件序列至少包含頁面識別、事件類型、按鈕識別、停留時間、返回次數、無效觸控次數、付款失敗次數、優惠券錯誤次數、購物車修改次數或閒置時間；根據該操作事件序列計算互動障礙觸發分數；當該互動障礙觸發分數達到一門檻時，擷取或取得多模態資料，該多模態資料包含影像、語音、語音辨識文字、情緒分析結果、POS 操作事件序列與 UI context；根據該多模態資料產生互動障礙狀態；根據該互動障礙狀態產生服務介入動作；以及根據該服務介入動作後的結果更新該門檻或介入策略。

2. 如請求項 1 所述的方法，其中該互動障礙狀態包含付款卡關、優惠券卡關、操作困惑、菜單選擇猶豫、等待不耐、需要真人協助、疑似抱怨、資訊不足或正常操作。

3. 如請求項 1 所述的方法，其中該服務介入動作包含顯示付款教學、顯示優惠券提示、顯示操作提示、切換簡化介面、推薦熱門組合、暫停促銷推播、發出語音協助或通知真人客服。

4. 如請求項 1 所述的方法，其中該多模態資料僅於互動障礙觸發分數達到門檻時擷取或分析，以降低持續影像分析的運算成本與顧客影像保存量。

5. 如請求項 1 所述的方法，其中該服務介入動作後的結果包含付款是否成功、結帳是否成功、是否通知店員或介入後完成結帳所需時間，並用於調整後續互動障礙觸發門檻或服務介入策略。

## 5.1 事件觸發式多模態流程步驟

S1：POS 端在記憶體中維持最近 5 秒 rolling buffer，預設不保存原始影像檔。

S2：POS 端發生異常事件，例如付款失敗、優惠券錯誤、無效觸控、長時間停留或返回上一頁，並上報 `interaction_event`。

S3：後端根據最近事件窗口計算 `risk_score` 與觸發原因。

S4：若 `risk_score` 達到門檻，POS 端錄製觸發後 5 秒，並與觸發前 5 秒合併為約 10 秒短片段。

S5：後端執行 Whisper 語音辨識、media_signals 分析與 Emotion-LLaMA 情緒/行為證據擷取。

S7：系統建立 `multimodal_evidence`，包含視覺證據、語音證據、情緒證據與 POS 事件證據。

S8：Barrier State Engine 將 `multimodal_evidence`、POS 事件與 UI context 推理為 `barrier_state`。

S9：Intervention Pipeline Service 統一呼叫 Barrier State Engine 與 Intervention Engine，根據 `barrier_state` 產生 `intervention_action`，並保存 `intervention_log`。

S10：系統透過 WebSocket 將介入建議即時推送至 POS 與後台 Admin。

S11：顧客完成 checkout 後，系統回寫 `intervention_result`，形成「偵測 → 介入 → 成效回饋」閉環。

## 6. 隱私保護實施例

在一實施例中，系統平時不保存顧客原始影像或完整語音，只保存匿名化 POS 操作事件，例如頁面、事件類型、停留時間、返回次數、付款失敗次數、無效觸控次數與購物車修改次數。該等事件可被轉換為事件向量或統計特徵，用於計算互動障礙風險分數。

當風險分數未達門檻時，系統不啟動多模態分析，也不保存原始影片片段。當風險分數達門檻時，系統可僅保存 `barrier_state`、`intervention_action`、`intervention_result`、情緒分佈、人物偵測框座標或音量 / 動作等摘要訊號，而不保存原始影像。

在需要稽核或模型改善的情境中，系統可透過設定開啟短時間原始片段保存，並設定保留時間，例如 10 分鐘。保留時間到期後，系統刪除原始片段，但保留匿名化事件向量、互動障礙狀態與介入成效，用於統計與策略調整。

## 7. 低算力實施例

在一實施例中，系統不對攝影機畫面做連續大型模型推論，而是先以低成本 POS 操作事件計算互動障礙風險分數。該計算可由本地規則完成，例如付款失敗、優惠券錯誤、同頁停留過久、返回次數過多或無效觸控過多。

只有當風險分數達到門檻時，系統才啟動較高成本的多模態分析，例如 Whisper 語音辨識、Emotion-LLaMA 情緒分析或 LLM 介入決策。如此可降低 GPU / CPU 使用率、縮短平均回應延遲、減少裝置發熱，並使自助點餐機可在較低硬體規格下運行。

系統亦可根據設備負載調整門檻、影像片段長度或推論頻率。例如在尖峰時段提高觸發門檻、縮短片段長度，或僅使用事件向量與語音文字推論。

## 8. 事件觸發短片段擷取實施例

在一實施例中，系統設定觸發前事件緩衝時間與觸發後事件緩衝時間，例如 `INTERACTION_PRE_EVENT_BUFFER_SEC=5` 與 `INTERACTION_POST_EVENT_BUFFER_SEC=5`。當互動障礙風險分數達到門檻時，系統只擷取或分析觸發點附近的短片段與事件序列。

短片段可包含觸發前後的影像、語音、語音文字、人物偵測結果、動作幅度、音量訊號、當前 UI 頁面與 POS 操作事件。系統以該短片段推論 `barrier_state`，再產生對應的 `intervention_action`。

若隱私設定禁止保存原始片段，系統仍可在記憶體中完成短片段分析，分析後只保存匿名化 metadata。若隱私設定允許保存原始片段，系統可在保留時間到期後自動清除原始檔，保留後續統計所需的事件向量與介入結果。

## 9. 事件觸發式多模態分析 API 實施例

在一實施例中，系統提供 `/api/triggered_multimodal_analysis`。該 API 僅在互動障礙風險達門檻後被呼叫，輸入包含短影片片段、互動風險結果、UI context 與 POS 操作摘要。系統先分析音量、動作與人物偵測，再進行 Whisper 語音辨識與 Emotion-LLaMA 證據擷取。

Emotion-LLaMA prompt 會附帶目前 POS 頁面、風險分數、觸發原因與互動摘要，但明確限制模型不得做服務決策，只能提供情緒與行為證據。後續由 Barrier State Engine 與 Intervention Engine 產生 `barrier_state` 與 `intervention_action`。

此 API 可在不持續分析所有影像的前提下，保留多模態判斷能力；若隱私設定不保存原始片段，系統只回傳或保存 `multimodal_evidence`、`barrier_state`、`intervention_action` 與 `intervention_result`，降低影像資料長期保存風險。
