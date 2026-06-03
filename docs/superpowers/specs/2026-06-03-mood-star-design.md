# 心情動態星星功能 — 設計規格

**日期：** 2026-06-03
**版本：** 1.0

---

## 1. 功能概述

在 POS kiosk 首頁加入「心情星星選擇器」（1–5 顆星），讓顧客在開始點餐前選擇當下心情。心情資料儲存在後端 session，並注入 AI 推播、語音助理、猶豫彈跳視窗的 prompt，使推薦更貼近顧客當下狀態。未選擇心情時，所有 AI 行為維持原有邏輯，不產生任何影響。

---

## 2. 決策摘要

| 議題 | 決策 |
|------|------|
| 星星顯示方式 | 5 顆獨立星星，點第 N 顆 → 第 1–N 顆亮起（金黃色 + 彈跳動畫），再點同顆取消 |
| 心情對 AI 的影響 | C：品項偏好 + 語氣同時調整 |
| Prompt 設定位置 | settings.json，共 5 個 key（MOOD_CONTEXT_1..5）統一注入所有 AI 服務 |
| 心情可否中途修改 | 不可；整個 session 固定 |
| 架構方式 | A：後端 session 儲存；選完後呼叫 `POST /api/session/mood` |

---

## 3. 資料模型

### 3.1 Session 狀態（session_repository）

`session_db[session_id]` 新增欄位：

```python
{
    "mood_score": 0,   # 0 = 未選擇，1–5 = 選了幾顆星
    "mood_label": ""   # "很差" / "普通" / "還不錯" / "很開心" / "超棒" / ""
}
```

`mood_score = 0` 時所有 AI 行為與現在完全相同，不注入任何 mood context。

### 3.2 Checkout Log 新增欄位

```json
{
  "mood_score": 3,
  "mood_label": "還不錯"
}
```

### 3.3 Admin 統計 API 回應新增欄位

```json
{
  "mood_hit_rate": 0.68,
  "mood_total": 168,
  "mood_sessions": 247,
  "mood_distribution": { "1": 20, "2": 30, "3": 59, "4": 42, "5": 17 }
}
```

---

## 4. Settings.json 新增設定

`DEFAULT_SETTINGS` 與 `settings.json` 新增以下 5 個 key（可由 admin 後台即時熱改）：

```json
"MOOD_CONTEXT_1": "顧客今天心情很差（1星）。優先推薦薯條、麥脆雞等撫慰系餐點；語氣溫柔體貼，例如「今天辛苦了，讓美食陪伴你」。避免強調慶祝或升級。",
"MOOD_CONTEXT_2": "顧客今天心情普通（2星）。推薦熱門主餐如大麥克、麥香魚；語氣自然親切，不過度熱情。",
"MOOD_CONTEXT_3": "顧客今天心情還不錯（3星）。推薦均衡熱門組合或套餐；語氣友善正向，可適度推薦加購。",
"MOOD_CONTEXT_4": "顧客今天心情很開心（4星）。推薦升級套餐或加大；語氣開朗，可用輕度慶祝語氣，例如「心情好，就來份大份的！」。",
"MOOD_CONTEXT_5": "顧客今天心情超棒（5星）。推薦限定款、高價位或雙份餐；語氣活潑慶祝，例如「心情超好！來份大麥克犒賞自己！」。"
```

空字串 `""` 代表該星等不注入（走原始行為）。

---

## 5. 後端架構

### 5.1 新建檔案

#### `backend/services/mood_service.py`

```python
# 唯一職責：從 session 讀取 mood_score，回傳對應的 mood context 字串
def get_mood_context(session_id: str) -> str
def get_mood_labels() -> dict[int, str]  # {1:"很差", 2:"普通", ...}
```

#### `backend/routes/mood_routes.py`

```
POST /api/session/mood
  body: { session_id: str, mood_score: int (1–5) }
  → session_repository.set_session_mood()
  → { status: "ok", mood_score: n, mood_label: "..." }
```

### 5.2 修改檔案

| 檔案 | 變更 |
|------|------|
| `config.py` | DEFAULT_SETTINGS 加入 MOOD_CONTEXT_1..5 |
| `learning_data/settings.json` | 同步加入 MOOD_CONTEXT_1..5 |
| `backend/repositories/session_repository.py` | 新增 `set_session_mood()` / `get_session_mood()` |
| `backend/services/voice_service.py` | 在組 system_prompt 後，prepend mood context（若 score > 0）|
| `backend/services/ai_push_service.py` | 在 user prompt 加入 `【顧客心情參考】` 段落 |
| `backend/services/recommendation_service.py` | 猶豫彈跳視窗推薦時注入 mood context |
| `backend/database.py` | `record_final_checkout()` 帶入 mood_score / mood_label |
| `backend/routes/core_routes.py` | 統計 API 加入 mood 聚合計算 |
| `main.py` | 註冊 mood_routes |

### 5.3 Mood Context 注入方式

各服務注入位置與格式統一：

```
【顧客心情參考】
{mood_context}

（原有 system prompt 或 user prompt 內容）
```

`mood_score = 0`（未選）：不加任何段落，完全透明。

---

## 6. 前端架構

### 6.1 POS 首頁（`pos/index.html` + `pos/app.js`）

**現有 startup overlay 改版：**

```
┌─────────────────────────────────────┐
│ 🍟  歡迎來點今天的好心情             │
│     Welcome / Start Your Order      │
│     ✦ 先選擇今天的心情，再開始點餐   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │  今天心情如何？               │   │
│  │  Tap the stars...            │   │
│  │                              │   │
│  │  ☆  ☆  ☆  ☆  ☆            │   │
│  │  很差 普通 還不錯 很開心 超棒  │   │
│  └─────────────────────────────┘   │
│                                     │
│  [黑色] 開始點餐                    │  ← 未選
│  [紅色] 開始點餐 😊 還不錯          │  ← 選了 3 星
└─────────────────────────────────────┘
```

**互動邏輯（`app.js`）：**

```javascript
let currentMoodScore = 0;  // 0 = 未選

function selectMood(n) {
  currentMoodScore = (currentMoodScore === n) ? 0 : n;  // 再點同顆取消
  renderStars();
}

// 按「開始點餐」時
async function startOrdering() {
  if (currentMoodScore > 0) {
    await fetch('/api/session/mood', {
      method: 'POST',
      body: JSON.stringify({ session_id, mood_score: currentMoodScore })
    });
  }
  // 進入點餐流程（原有邏輯）
  enterOrderingMode();
}
```

### 6.2 Admin 後台

**統計頁新增 widget：**
- 心情觸擊率（大數字）= 選了星星的 session 數 / 總 session 數 × 100%
- 心情分佈橫條圖（各星等次數與百分比）

**訂單明細新增欄位：**
- 「心情」欄，顯示彩色標籤（1星紅 / 2星橙 / 3星黃 / 4星綠 / 5星藍 / 未選灰）

---

## 7. 可行性評估

**整體：完全可行 ✅**

| 面向 | 評估 |
|------|------|
| 後端改動 | 中等，符合現有分層架構，新建 2 個檔案，修改 8 個 |
| 前端改動 | 中等，主要集中在 index.html startup overlay 重構與 app.js |
| AI 影響邊界 | 清晰；mood_score=0 時完全透明，不破壞現有行為 |
| 設定可控性 | 高；5 個 MOOD_CONTEXT 全在 settings.json，admin 熱改即生效 |
| 統計準確性 | 高；mood 在後端 session 記錄，checkout 時寫入 log |
| 風險 | 低；mood context 只是額外的 prompt 前綴，不改變任何核心流程 |

**預估影響檔案：**

```
新建（2）：
  backend/services/mood_service.py
  backend/routes/mood_routes.py

修改（12）：
  config.py
  learning_data/settings.json
  main.py
  backend/repositories/session_repository.py
  backend/services/voice_service.py
  backend/services/ai_push_service.py
  backend/services/recommendation_service.py
  backend/database.py
  backend/routes/core_routes.py
  frontend/pos/index.html
  frontend/pos/app.js
  frontend/admin/admin.html  (+ admin.js)
```

---

## 8. 不在此版本範圍

- 心情對 TTS 語速/音調的影響（可後續擴充）
- 跨 session 的心情趨勢分析（可後續擴充）
- 多語系心情標籤（目前僅繁體中文）
