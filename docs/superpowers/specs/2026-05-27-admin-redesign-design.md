# Admin 端完整重設計

**日期**：2026-05-27  
**範圍**：刪除現有 admin HTML/JS，重寫為白色簡潔、儀表板優先的專利展示後台

---

## 背景與目標

現有 admin 為 8-tab 結構（486 行 HTML），包含大量 RAG 內部調參、除錯工具、非核心設定，不適合作為專利展示介面。

**目標**：建立以「即時監控儀表板」為首頁、白色簡潔風格的新後台，讓評審打開第一眼即看到核心專利流程的運作狀態，並可快速切換至必要的設定與資料頁面。

---

## 設計決策

| 面向 | 決策 |
|---|---|
| 定位 | 專利展示用（非運維用、非開發用） |
| 佈局 | 儀表板優先 + 底部導航列 |
| 風格 | 白色簡潔（`#f8fafc` 背景、白色卡片、紫色 accent） |
| 結構 | 單一 HTML + JS show/hide，五個畫面 |

---

## 畫面架構

```
預設：儀表板（adminSection = 'dashboard'）
  ↓ 點底部圖示
  ├── 😊 Emotion / AI 設定 (adminSection = 'emotion')
  ├── 🎬 影像片段        (adminSection = 'clips')
  ├── 🍔 菜單管理        (adminSection = 'menu')
  └── 📄 RAG 知識庫      (adminSection = 'rag')

每個設定頁頂部有「← 返回監控」按鈕，切回 dashboard
```

---

## 儀表板設計

### 頂部列
- 左：系統名稱「智慧自助點餐介入系統」+ 副標「後台管理」
- 右：LIVE 狀態標籤（綠色 badge）+ 當前 Session ID

### 三格指標卡片（`grid-template-columns: 1fr 1fr 1fr`）

| 卡片 | 主要數值 | 次要資訊 |
|---|---|---|
| 風險指數 | `risk_score`（大字體，紫色）+ 水平進度條 | level（stable/watch/assist/urgent/critical） |
| 情緒狀態 | `emotion_label`（含 emoji） | 信心度數值 |
| 障礙類型 | `barrier_state`（英文 key） | 觸發來源描述 |

### 介入動作橫幅
- 紅色漸層背景（`#fef2f2`）+ 紅色邊框
- 左：`intervention_action` 名稱（加 ⚡ 前綴）
- 右：「已推送 POS」+ 時間戳
- 若無介入動作，顯示「目前無介入」灰色橫幅

### 最近事件 Log
- 最新 3 筆，格式：`HH:MM:SS  事件描述`
- 每筆右側有 level badge（stable/watch/urgent 用不同底色）
- 透過 WebSocket (`/ws/admin/{session_id}`) 即時更新

### 底部導航列
- 固定在 admin 區塊底部（非 viewport 固定，隨頁面內容排版）
- 4 格等寬：😊 Emotion/AI、🎬 影像片段、🍔 菜單管理、📄 RAG 知識庫
- 當前選中頁面的按鈕顯示紫色背景高亮（儀表板時全部無高亮）

---

## Emotion / AI 設定頁

四個白色卡片，垂直排列：

### 卡片 1：情緒偵測（紫色標題）
| 欄位 | 對應設定鍵 | 預設值 |
|---|---|---|
| 偵測間隔（秒） | `EMOTION_MIN_GAP_SEC` | 12 |
| 影片截取長度（秒） | `EMOTION_CLIP_DURATION` | 3 |
| 音量門檻（dBFS） | `WHISPER_LOW_AUDIO_DB` | -58 |
| 推播最短間隔（秒） | `PUSH_MIN_INTERVAL_SEC` | 30 |

### 卡片 2：LLM 推論（藍色標題）
| 欄位 | 對應設定鍵 | 預設值 |
|---|---|---|
| 推論溫度 | `OLLAMA_TEMPERATURE` | 0.7 |
| 輸出上限（tokens） | `OLLAMA_MAX_TOKENS` | 512 |
| 問答來源 | `QA_SERVICE` | Ollama（本地）|

### 卡片 3：Prompt 設定（綠色標題）
| 欄位 | 對應設定鍵 |
|---|---|
| 語音問答 Prompt（繁中） | `VOICE_SYSTEM_PROMPT_ZH` |
| 推播推薦 Prompt | `PUSH_SYSTEM_PROMPT` |

（textarea，可多行輸入）

### 卡片 4：答案品質（黃色標題）
| Checkbox | 對應設定鍵 |
|---|---|
| 嚴格來源限制 | `RAG_CONFIG.strict_grounding` |
| LLM 答案驗證 | `RAG_CONFIG.answer_verification` |
| 評估失敗時拒答 | `RAG_CONFIG.fail_closed` |

底部：**「儲存設定」按鈕**（紫色，全寬），呼叫 `POST /api/settings`

---

## 影像片段頁

- 重用現有 `GET /api/emotion_clips/{session_id}` API
- 卡片 Grid（2 欄），每張卡片顯示：
  - 情緒標籤 badge（含 emoji）
  - risk_score
  - 時間戳
  - 「播放」按鈕（呼叫 `/api/emotion_clips/{session_id}/media/{clip_id}`）
- 頂部：「共 N 筆」+ 清除按鈕（呼叫 `DELETE /api/emotion_clips/{session_id}`）

---

## 菜單管理頁

- 重用現有 `GET /api/menu`、`POST /api/menu` API
- 品項列表（含名稱、價格、分類）
- 每筆右側有「編輯」按鈕（點後展開 inline 表單，POST 覆寫）
- 頂部「新增品項」按鈕，點後顯示 inline 表單

---

## RAG 知識庫頁

- 重用現有 `GET /api/rag_docs`、`POST /api/rag_docs`、`POST /api/rag_pdf`、`DELETE /api/rag_docs/{doc_id}` API
- 文件列表（含名稱、類型、建立時間）
- 上傳區：文字貼上（`POST /api/rag_docs`）+ PDF 上傳（`POST /api/rag_pdf`）
- 每筆文件右側有「刪除」按鈕

---

## 刪除範圍

### HTML（`UI_API/index.html`）
- 刪除整個 admin 區塊內容（現有 8 個 tab：儀表板、功能模組、Emotion功能、AI設定、影像片段、菜單管理、RAG文本、語音協助），約 486 行
- 保留 admin 外層容器 `<div id="adminPanel">` 以及 port 8001 路由邏輯
- 重寫為新的五畫面結構

### JS（`UI_API/static/app.js`）
刪除並重寫以下函式：
- `loadAdminData()`
- `loadSettings()` / `saveSettings()`
- `initAdminToggles()`
- `loadEmotionStatus()`
- `loadEmotionClips()`
- `loadRagData()`
- `switchAdminTab()`

新增：
- `switchAdminSection(section)` — show/hide 五個畫面
- `loadDashboard()` — 讀取最新 risk_score、emotion、barrier、intervention，填入儀表板
- `loadEmotionSettings()` / `saveEmotionSettings()` — Emotion/AI 設定頁
- `loadClipsPage()` — 影像片段頁
- `loadMenuPage()` / `saveMenuItem()` — 菜單管理頁
- `loadRagPage()` / `uploadRagDoc()` — RAG 知識庫頁

### 不動
- 後端所有 routes / services / repositories
- POS 前端（`app.js` 中非 admin 的部分）
- WebSocket 連線邏輯（僅更新 admin 端的事件處理 handler）

---

## 資料流

```
WebSocket /ws/admin/{session_id}
  → 收到 risk_event / emotion_result / intervention_action
  → 呼叫 updateDashboard(data)
  → 更新三格指標 + 介入橫幅 + 事件 Log（prepend，最多保留 3 筆）

POST /api/settings（儲存設定）
  → 回傳 { success: true }
  → 顯示儲存成功 toast（2 秒後自動消失）
```

---

## 設定鍵對應確認

所有設定鍵均已存在於 `config.py` 的 `DEFAULT_SETTINGS`，本次不新增設定鍵。  
`RAG_CONFIG` 使用 `_existingRag` spread 模式保留未對應欄位（沿用上一版修法）。
