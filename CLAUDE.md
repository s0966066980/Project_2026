# Project_2026 — 智慧自助點餐與客服介入系統

## 專案概述

麥當勞台灣自助點餐 kiosk 原型系統，核心功能包含：
- 語音點餐（Whisper STT → Ollama LLM → Edge TTS）
- AI 推播（底部推薦欄）與猶豫彈跳視窗
- 互動障礙偵測（POS 事件 + 語音 → barrier_state → intervention）
- WebSocket 即時通訊（POS / Admin）
- 後台統計與設定管理

Emotion-LLaMA 目前為 **stub**（預留對接介面），尚未接入。

---

## Tech Stack

- **後端**：Python 3.x、FastAPI（port 8000 + 8001）
- **前端**：Vanilla JS（ES modules，無框架）
- **AI 推論**：Ollama（qwen3.5:4b）、可選 Gemini API
- **語音**：Whisper（本地 STT）、Edge TTS
- **視覺**：Emotion-LLaMA（stub，port 7889 預留）
- **資料庫**：JSON 檔（session/log/menu）
- **設定**：`.env`（靜態）+ `learning_data/settings.json`（後台即時讀寫）

---

## 專案結構

```
Project_2026/
├── CLAUDE.md
├── UI_API/
│   ├── main.py                        ← 唯一入口，啟動 8000/8001
│   ├── config.py                      ← 靜態設定 + 動態設定管理器
│   ├── backend/
│   │   ├── ai_services.py             ← Whisper、Ollama、Gemini、TTS
│   │   ├── database.py                ← 菜單 context、checkout log
│   │   ├── routes/                    ← FastAPI endpoints
│   │   ├── services/                  ← 業務邏輯
│   │   ├── repositories/              ← JSON 資料存取
│   │   ├── realtime/                  ← WebSocket event bus
│   │   ├── utils/                     ← 共用工具
│   │   ├── prompts/defaults.py        ← LLM system prompt 預設值
│   │   └── menu_data/menu.json        ← 菜單（MCDxxx 格式）
│   ├── frontend/
│   │   ├── pos/                       ← POS kiosk (index.html, app.js, cart.js, media.js)
│   │   ├── admin/                     ← 後台 (admin.html, admin.js)
│   │   └── shared/                    ← 共用 (api.js, ui.js, styles.css, ...)
│   ├── learning_data/                 ← Runtime 資料（不提交 git）
│   └── menu_data/                     ← 菜單（config.py 路徑依賴）
└── Emotion-LLaMA/
    └── app_EmotionLlamaClient.py      ← 情緒推論服務（port 7889，可選）
```

---

## 啟動方式

```bash
# 主服務（必要）
cd UI_API && conda activate emotion_ui
python main.py
# POS：http://127.0.0.1:8000
# 後台：http://127.0.0.1:8001

# Emotion-LLaMA（可選，stub 狀態下不需要）
cd Emotion-LLaMA && conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889

# Ollama（必要）
ollama serve
ollama pull qwen3.5:4b
```

---

## 架構規則（修改前必讀）

### 分層職責
- **routes/**：只做請求解析、呼叫 service、回傳 response。**不放業務邏輯。**
- **services/**：業務邏輯主體。不直接讀寫 JSON，透過 repository。
- **repositories/**：JSON 資料存取。**不放業務邏輯、不做 AI 呼叫。**
- **ai_services.py**：所有 AI 呼叫（Whisper、Ollama、Gemini、TTS）集中在此。

### 設定系統
- 靜態設定（port、API key）寫在 `.env`，由 `config.py` 讀取。
- 動態設定（AI 參數、功能開關）存在 `learning_data/settings.json`，後台可即時修改。
- **讀設定統一用 `config.get("KEY")`**，不要直接讀 `os.getenv`。

### 菜單白名單
- 菜單來源：`menu_data/menu.json`（ID 格式：`MCDxxx`）。
- 語音點餐、AI 推播的品項必須通過白名單校正，**不允許 LLM 幻覺餐點**。

### WebSocket
- 統一入口：`/ws/{client_type}/{session_id}`
- `client_type`：`pos`、`admin`
- 事件推送透過 `realtime/event_bus.py`，**不在 route 或 service 直接操作連線**。

### Port 隔離
- `8000`：永遠是 POS 客戶端。
- `8001`：永遠是後台管理（獨立 admin.html）。
- **不要修改這個邏輯。**

---

## 禁止事項

- **不要在 route 直接呼叫 ai_services**，一律透過 service layer。
- **不要在 service 直接讀寫 JSON**，透過 repository。
- **不要在 checkout 加阻擋邏輯**，checkout 應永遠可以完成。
- **不要提交 `.env`、`learning_data/` runtime 資料。**
- **不要修改菜單 ID 格式（MCDxxx）**。

---

## 核心業務流程

### 語音點餐
```
音訊上傳 → Whisper STT → 組 prompt（TODO: RAG slot）
→ Ollama LLM → 解析 ai_response + cart_actions → Edge TTS → 回傳
```

### AI 推播
```
前端定時呼叫 → Ollama 從菜單白名單選 1 品 → 回傳推薦 + 促購短句
→ 前端底部欄顯示
```

### 互動障礙介入
```
POS 操作事件 → POST /api/interaction_event（保存）
→ 語音輸入 / 手動觸發 → POST /api/barrier_state
→ barrier_state_service（事件計數 + 語音判斷）
→ intervention_service（決定 action）
→ WebSocket 推送介入卡給 POS
→ checkout 後回寫 intervention_result（閉環）
```

### 猶豫彈跳視窗
```
購物車空且無操作 60 秒 → 前端顯示推薦彈窗
→ 顧客點選 → trackedAddToCart（source: choice_hesitation）
```

---

## barrier_state 與 intervention_action 對照

| barrier_state | intervention_action |
|---|---|
| `normal_operation` | `none` |
| `menu_hesitation` | `recommend_popular_combo` |
| `operation_confusion` | `show_operation_hint` |
| `payment_confusion` | `show_payment_tutorial` |
| `coupon_confusion` | `show_coupon_guide` |
| `impatience_detected` | `call_staff_or_fast_mode` |
| `service_needed` | `call_staff` |
| `potential_complaint` | `call_staff` |
| `low_confidence` | `ask_clarifying_question` |

---

## 常用開發檢查

```bash
# Python 語法檢查
python3 -m py_compile main.py config.py
python3 -m py_compile backend/services/barrier_state_service.py
python3 -m py_compile backend/routes/core_routes.py

# JS 語法檢查
node --check frontend/pos/app.js
node --check frontend/shared/api.js

# 啟動後確認服務
curl http://127.0.0.1:8000/api/public_settings
curl http://127.0.0.1:8001/api/settings
```

---

## 目前 Sprint / 進行中工作

- 程式碼重構清理（code review 系列）

---

## 相關文件

- `UI_API/README.md`：API 完整清單、前後端架構說明
- `UI_API/CODEBASE.md`：每個檔案的職責與程式碼架構詳細說明
- `UI_API/PATENT_DESIGN.md`：專利設計草稿
