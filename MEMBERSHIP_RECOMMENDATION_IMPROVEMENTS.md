# 會員推薦與語音個人化改進項目

日期：2026-06-30

本文件整理會員推薦系統的後續修改項目，重點說明每一項要改哪些部分、改動重點、影響範圍、預期效果與建議執行順序。此文件只作為規劃與需求說明，不代表已完成程式碼修改。

## 一、目標

目前會員系統已經可以記錄常點與歷史訂單，AI 推播也會根據會員常點加權。下一階段的目標是讓會員點餐紀錄成為整個推薦系統的核心訊號，影響：

- 語音模式推薦
- AI 推播推薦
- 輔助推薦
- 常點復購
- RAG 活動與會員優惠推薦

最終希望達成：

```text
會員登入
  ↓
讀取會員歷史點餐
  ↓
產生會員偏好摘要
  ↓
結合目前購物車、菜單、熱門品項、RAG 活動資訊
  ↓
產生個人化推薦
  ↓
記錄推薦是否被接受
  ↓
下一次推薦更準
```

## 二、建議執行順序

| 順序 | 項目 | 優先級 | 原因 |
| --- | --- | --- | --- |
| 1 | 會員推薦上下文整合 | 高 | 讓語音、AI 推播、輔助推薦有共同資料基礎 |
| 2 | 語音模式加入會員偏好 | 高 | 使用者體感最明顯 |
| 3 | 統一推薦引擎 | 高 | 避免各推薦入口邏輯分散 |
| 4 | 推薦事件紀錄 | 高 | 後續優化與商用分析的基礎 |
| 5 | 修正會員偏好統計 | 中高 | 提高推薦準確度 |
| 6 | 會員資料儲存升級 | 中 | 商用必要，但工程量較大 |
| 7 | 會員登入安全升級 | 中 | 商用前必做 |
| 8 | Admin 會員管理升級 | 中 | 方便營運與客服 |
| 9 | RAG 與會員推薦結合 | 中 | 活動、優惠、規則可正確影響推薦 |
| 10 | 商用監控與測試 | 中 | 確保推薦與會員流程可維運 |

## 三、改進項目詳細說明

## 1. 會員推薦上下文整合

### 目的

建立一個共用的推薦上下文，讓 AI 推播、語音模式、輔助推薦都能取得一致的會員偏好資料。

### 目前狀況

目前會員資料主要在 `member_service` 中使用，AI 推播會直接讀取會員常點。語音模式尚未完整注入會員偏好。

### 建議修改部分

新增服務：

```text
UI_API/backend/services/recommendation_context_service.py
UI_API/backend/services/member_preference_service.py
```

可能調整：

```text
UI_API/backend/services/member_service.py
UI_API/backend/services/ai_push_service.py
UI_API/backend/services/voice_service.py
UI_API/backend/routes/ai_push_routes.py
```

### 核心資料

推薦上下文應包含：

```json
{
  "session_id": "pos_xxx",
  "member": {
    "phone_masked": "0912-***-678",
    "nickname": "小明",
    "visit_count": 8,
    "avg_spend": 180
  },
  "preferences": {
    "usual_items": ["MCD001", "MCD012"],
    "recent_items": ["MCD001"],
    "preferred_categories": ["超值全餐", "點心"],
    "last_order_items": ["MCD001", "MCD012"]
  },
  "cart": {
    "item_ids": ["MCD001"],
    "total": 155
  }
}
```

### 修改重點

- 不要讓各服務自己重複組會員資料。
- 不要把會員個資直接丟進 LLM prompt。
- 只給語音與推薦需要的摘要。
- 沒有會員時要回傳訪客上下文。
- 上下文產生失敗不能阻擋推薦或語音。

### 預期效果

- 語音、AI 推播、輔助推薦開始使用一致的會員偏好。
- 後續新增策略時不需要改多個服務。

## 2. 語音模式加入會員偏好

### 目的

讓會員問「推薦什麼」、「幫我點我常吃的」、「跟上次一樣」時，語音模式可以根據會員歷史點餐回應。

### 目前狀況

語音模式目前主要使用：

- 菜單內容
- 對話歷史
- 熱門 TOP 3
- RAG
- 情緒資訊

但沒有完整使用會員常點與歷史訂單。

### 建議修改部分

主要修改：

```text
UI_API/backend/services/voice_service.py
```

可能新增：

```text
UI_API/backend/services/voice_member_context_service.py
```

### 語音 prompt 應新增內容

範例：

```text
【會員偏好摘要】
會員暱稱：小明
常點品項：大麥克套餐、薯條、零卡可樂
最近一筆訂單：大麥克套餐 + 薯條
偏好分類：牛肉主餐、套餐
目前購物車：尚未加入餐點

若顧客詢問推薦，請優先考慮會員偏好，但不要捏造菜單不存在的餐點。
若顧客說「幫我點我常吃的」，請先確認是否加入購物車，不要未確認直接加購。
```

### 修改重點

- 會員偏好只注入精簡摘要，不注入完整訂單 JSON。
- 語音回答要自然，不要透露內部欄位。
- 顧客沒有明確下單意圖時，`cart_actions` 必須保持空陣列。
- 顧客明確說「幫我加常點」時，才可產生 cart action。
- 若會員沒有歷史，回退到熱門品項與 RAG 活動。

### 預期效果

會員語音推薦會更像個人化助理，而不是單純菜單問答。

## 3. 統一推薦引擎

### 目的

目前 AI 推播、輔助推薦與語音推薦邏輯容易分散。建議建立統一推薦引擎，讓不同入口共用候選品項與打分邏輯。

### 建議新增服務

```text
UI_API/backend/services/recommendation_candidate_service.py
UI_API/backend/services/recommendation_scoring_service.py
UI_API/backend/services/recommendation_engine_service.py
```

### 推薦候選來源

候選品項應來自：

- 會員常點
- 最近訂單
- 目前購物車搭配
- 熱門品項
- RAG 活動或會員優惠
- 菜單主推分類
- 新品或商業主推品項

### 打分方式

初期建議用規則分數：

```text
score =
  會員常點分數
+ 最近點餐分數
+ 分類偏好分數
+ 購物車搭配分數
+ 活動優惠分數
+ 熱門品項分數
+ 時段適合分數
- 已在購物車懲罰
- 最近已推薦懲罰
- 會員曾忽略懲罰
```

### 回傳格式

推薦引擎建議回傳：

```json
{
  "item_id": "MCD001",
  "strategy": "reorder",
  "score": 82,
  "reason": "會員常點且最近曾購買",
  "personalized": true
}
```

### 修改重點

- AI push 不再自己做完整推薦邏輯，只負責展示與產生文案。
- Assist recommendation 不再重複呼叫三次隨機推薦。
- 語音模式可要求推薦引擎提供候選，再由 LLM 生成自然語句。
- 推薦品項必須永遠來自菜單白名單。

### 預期效果

- 推薦邏輯一致。
- 比較容易測試。
- 容易知道為什麼推薦某品項。
- 後續可以加活動、會員、時段策略。

## 4. 推薦事件紀錄

### 目的

商用推薦系統不能只「推薦」，還要知道推薦是否有效。

### 建議新增紀錄

每次推薦應記錄：

- 推薦曝光
- 點擊
- 加入購物車
- 最後是否購買
- 忽略
- 推薦來源與策略

### 建議新增檔案或資料表

短期 JSON：

```text
UI_API/learning_data/recommendation_events.json
```

商用 DB：

```text
recommendation_events
```

### 建議欄位

```json
{
  "event_id": "rec_xxx",
  "session_id": "pos_xxx",
  "member_id": "member_xxx",
  "surface": "ai_push",
  "strategy": "pairing",
  "recommended_item_id": "MCD012",
  "shown_at": "2026-06-30T12:00:00",
  "clicked_at": "",
  "added_to_cart_at": "",
  "purchased_at": "",
  "ignored_at": ""
}
```

### 修改重點

- AI push 顯示時記錄 `shown`。
- 點擊加入時記錄 `clicked` / `added_to_cart`。
- checkout 時比對購物車，回寫 `purchased`。
- 若推薦被刷新或長時間未點擊，可記錄 `ignored`。

### 預期效果

- 可知道哪種策略有效。
- 可分析會員是否接受推薦。
- 可做後續 A/B test。

## 5. 修正會員偏好統計

### 目的

目前偏好統計較粗，應改成能反映真實點餐行為。

### 建議修改部分

```text
UI_API/backend/services/member_service.py
```

### 修改重點

- 同品項多份應累加數量。
- 記錄最近點餐時間。
- 記錄分類偏好。
- 記錄搭配組合。
- 可加入時間衰減，讓最近行為比很久以前更重要。

### 範例

目前可能只記：

```json
{
  "MCD012": 1
}
```

建議改成：

```json
{
  "MCD012": {
    "count": 3,
    "last_ordered_at": "2026-06-30T12:00:00",
    "category": "點心"
  }
}
```

### 預期效果

會員偏好更準，推薦不會只看粗略常點。

## 6. 會員資料儲存升級

### 目的

從 demo / MVP 的 JSON 儲存升級成可商用維運的資料庫。

### 建議資料表

```text
members
member_sessions
member_orders
member_order_items
member_preferences
recommendation_events
```

### 修改重點

- 使用 PostgreSQL 作為主要商用資料庫。
- session 可用 Redis 或 DB-backed session。
- 增加 migration。
- 增加備份與還原流程。
- 不要把訂單長期塞在 members JSON 裡。

### 預期效果

- 支援多 worker。
- 支援查詢與統計。
- 支援長期商用資料累積。

## 7. 會員登入安全升級

### 目的

避免手機號碼被冒用。

### 建議方式

可選其一：

- 手機 + OTP
- 手機 + PIN
- QR Code 會員碼
- 會員條碼

### 修改重點

- 登入失敗限制。
- per-phone / per-device rate limit。
- session TTL。
- 手機遮罩。
- audit log。

### 預期效果

會員身分更可信，符合商用最低安全要求。

## 8. Admin 會員管理升級

### 目的

讓營運與客服可以管理會員資料。

### 建議功能

- 會員搜尋
- 查看完整訂單
- 查看常點
- 清除點餐紀錄
- 刪除會員
- 匯出會員資料
- audit log
- 權限分級

### 修改重點

- 完整手機只給高權限角色。
- 一般後台只顯示 masked phone。
- 所有刪除與匯出都要記錄操作人。

## 9. RAG 與會員推薦結合

### 目的

RAG 提供活動、優惠、規則，會員資料提供個人化偏好，兩者合併後讓推薦更準確。

### RAG 適合放

- 活動規則
- 會員優惠
- 菜單補充
- 供應時間
- 營養與過敏原
- 客服 FAQ

### RAG 不應放

- 會員手機
- 會員訂單
- 個人偏好
- 付款資訊

### 修改重點

- 推薦時查詢 RAG 活動資訊。
- 若有會員優惠，增加對應推薦分數。
- 語音回答優惠時必須根據 RAG，不要讓 LLM 自行編造。

## 10. 商用監控與測試

### 目的

確保會員推薦系統穩定、可觀測、可優化。

### 建議測試

- 會員登入 / 註冊。
- 結帳後會員紀錄更新。
- 會員語音推薦。
- AI push 會員推薦。
- Assist recommendation 會員推薦。
- 推薦事件回寫。
- RAG 空資料 fallback。
- Chroma rebuild 不影響 POS。

### 建議監控

- 每日會員登入數。
- 會員推薦曝光數。
- 推薦點擊率。
- 推薦加購率。
- 推薦成交率。
- 熱門會員常點。
- 失敗登入次數。

## 四、建議先執行的三步

如果要最快看到產品效果，建議先做：

1. 會員推薦上下文整合。
2. 語音模式加入會員偏好。
3. 統一推薦引擎。

這三步完成後，會員點餐紀錄就能實際影響語音與推薦。

## 五、暫不建議優先做的項目

以下項目重要，但可以排在後面：

- PostgreSQL 完整 migration。
- OTP / PIN 完整登入。
- A/B testing。
- 推薦 dashboard。
- 複雜機器學習模型。

原因是目前最缺的是「會員紀錄尚未充分影響推薦體驗」，應先讓產品體驗成立，再做資料層與商用安全完整升級。
