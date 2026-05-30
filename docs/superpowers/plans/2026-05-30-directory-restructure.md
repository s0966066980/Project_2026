# Directory Restructure — backend/ + frontend/ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 `UI_API/` 重組為明確的前後端目錄結構：Python 程式碼移入 `backend/`，HTML/JS/CSS 移入 `frontend/`。

**Architecture:**
- `main.py`、`config.py` 保持根目錄。`backend/` 加入 `sys.path`，所有 backend 內部 import 完全不需修改。
- `frontend/` 掛載為 FastAPI 的 `/static/`；圖片資產放 `frontend/` 根目錄（非子目錄），保持 URL 不變。
- JS 按功能分：`frontend/pos/`（POS）、`frontend/admin/`（後台）、`frontend/shared/`（共用）。

**Tech Stack:** Python 3.x, FastAPI, Vanilla JS (ES modules)

---

## 目標目錄結構

```
UI_API/
├── main.py                    ← 根目錄（不動）
├── config.py                  ← 根目錄（不動）
├── requirements.txt
├── .env
│
├── backend/
│   ├── ai_services.py         ← 從根目錄移入
│   ├── database.py            ← 從根目錄移入
│   ├── routes/                ← 從根目錄移入
│   ├── services/              ← 從根目錄移入
│   ├── repositories/          ← 從根目錄移入
│   ├── realtime/              ← 從根目錄移入
│   ├── utils/                 ← 從根目錄移入
│   └── prompts/               ← 從根目錄移入
│
├── frontend/
│   ├── pos/
│   │   ├── index.html         ← 從根目錄移入
│   │   ├── app.js             ← 從 static/ 移入
│   │   ├── cart.js
│   │   └── media.js
│   ├── admin/
│   │   ├── admin.html         ← 從根目錄移入
│   │   └── admin.js
│   ├── shared/
│   │   ├── api.js
│   │   ├── ui.js
│   │   ├── media_buffer.js
│   │   ├── realtime_client.js
│   │   └── styles.css
│   ├── mcd_categories/        ← 從 static/ 移入（URL 保持 /static/mcd_categories/）
│   ├── menu_images/           ← 從 static/ 移入（URL 保持 /static/menu_images/）
│   └── mcd_start.png
│
├── menu_data/                 ← 保持根目錄（config.py 路徑依賴）
└── learning_data/             ← 保持根目錄（runtime 資料）
```

---

## 關鍵設計決策

**sys.path 橋接**：`main.py` 開頭加入：
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
```
這讓所有 `backend/` 內的檔案完全不需修改任何 import。

**圖片資產放 `frontend/` 根**（非 `frontend/shared/assets/`）：
- `app.js` 硬編碼 `/static/mcd_categories/...` 和 `/static/menu_images/...`
- FastAPI 掛載 `frontend/` 為 `/static/`
- 所以圖片在 `frontend/mcd_categories/` → URL 仍是 `/static/mcd_categories/` ✓
- 無需修改 app.js 任何圖片路徑

**`menu_data/` 和 `learning_data/` 保持根目錄**：
- `config.py` 使用 `"./menu_data/menu.json"` 等相對路徑（相對 CWD）
- 移動會導致 config.py 路徑失效，風險高

---

## Task 1: 移動 Python 後端到 backend/

**Files:**
- Create: `backend/__init__.py`
- Move: `ai_services.py`, `database.py` → `backend/`
- Move: `routes/`, `services/`, `repositories/`, `realtime/`, `utils/`, `prompts/` → `backend/`
- Modify: `main.py` (加 sys.path + 更新靜態目錄路徑)

- [ ] **Step 1: 建立 backend/ 目錄與空 __init__.py**

```bash
mkdir -p backend
touch backend/__init__.py
```

- [ ] **Step 2: 移動根目錄 Python 檔案**

```bash
mv ai_services.py database.py backend/
```

- [ ] **Step 3: 移動 Python 套件目錄**

```bash
mv routes/ services/ repositories/ realtime/ utils/ prompts/ backend/
```

- [ ] **Step 4: 在 main.py 頂部加入 sys.path 橋接**

在 `main.py` 第 1 行加入（在所有 import 之前）：

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))
```

- [ ] **Step 5: Compile check**

```bash
python3 -m py_compile main.py && echo "main OK"
python3 -m py_compile config.py && echo "config OK"
python3 -m py_compile backend/ai_services.py backend/database.py && echo "backend root OK"
python3 -m py_compile backend/routes/core_routes.py backend/routes/voice_routes.py backend/routes/emotion_routes.py && echo "routes OK"
python3 -m py_compile backend/services/voice_service.py backend/services/emotion_service.py backend/services/barrier_state_service.py && echo "services OK"
```
期望：全部 OK

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move Python backend code into backend/ directory"
```

---

## Task 2: 建立 frontend/ 結構並移動前端檔案

**Files:**
- Create: `frontend/pos/`, `frontend/admin/`, `frontend/shared/`
- Move: HTML files, JS files, CSS, image assets from `static/`

- [ ] **Step 1: 建立 frontend 子目錄**

```bash
mkdir -p frontend/pos frontend/admin frontend/shared
```

- [ ] **Step 2: 移動 HTML 檔案**

```bash
mv index.html frontend/pos/index.html
mv admin.html frontend/admin/admin.html
```

- [ ] **Step 3: 移動 POS JS 檔案**

```bash
mv static/app.js static/cart.js static/media.js frontend/pos/
```

- [ ] **Step 4: 移動 Admin JS 檔案**

```bash
mv static/admin.js frontend/admin/
```

- [ ] **Step 5: 移動共用 JS/CSS 檔案**

```bash
mv static/api.js static/ui.js static/media_buffer.js static/realtime_client.js static/styles.css frontend/shared/
```

- [ ] **Step 6: 移動圖片資產到 frontend/ 根（保持 URL 不變）**

```bash
mv static/mcd_categories frontend/mcd_categories
mv static/menu_images frontend/menu_images
mv static/mcd_start.png frontend/mcd_start.png
```

- [ ] **Step 7: 確認 static/ 已空，刪除**

```bash
ls static/   # 應為空
rmdir static/
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move frontend assets into frontend/ directory structure"
```

---

## Task 3: 更新 app.js 的 ES module import 路徑

**Files:**
- Modify: `frontend/pos/app.js` (4 個 import 路徑更新)

`app.js` 現在在 `frontend/pos/`，共用模組在 `frontend/shared/`，需要更新跨目錄的 import 路徑。

- [ ] **Step 1: 更新 4 個 import 路徑**

找到 `frontend/pos/app.js` 的前幾行（目前是 1–23 行）：

原：
```javascript
import * as api from './api.js';
import { API_BASE } from './api.js';
import {
  ...
} from './ui.js';
import {
  ...
} from './media.js';
import { createCartManager } from './cart.js';
import { connectRealtime } from './realtime_client.js';
import {
  ...
} from './media_buffer.js';
```

只修改這 4 個的路徑（`./` → `../shared/`）：
- `from './api.js'` → `from '../shared/api.js'` (出現兩次，第 1、2 行)
- `from './ui.js'` → `from '../shared/ui.js'`
- `from './realtime_client.js'` → `from '../shared/realtime_client.js'`
- `from './media_buffer.js'` → `from '../shared/media_buffer.js'`

保持不變（同在 pos/ 目錄）：
- `from './media.js'` → 不動
- `from './cart.js'` → 不動

- [ ] **Step 2: 驗證修改**

```bash
head -25 frontend/pos/app.js
```
確認路徑已正確更新，且 `cart.js` 和 `media.js` 仍是 `./`。

- [ ] **Step 3: Commit**

```bash
git add frontend/pos/app.js
git commit -m "refactor: update app.js ES module imports for new directory structure"
```

---

## Task 4: 更新 HTML 路徑與 FastAPI 設定

**Files:**
- Modify: `frontend/pos/index.html`
- Modify: `frontend/admin/admin.html`
- Modify: `main.py` (靜態目錄路徑)
- Modify: `backend/routes/core_routes.py` (FileResponse 路徑)

- [ ] **Step 1: 更新 frontend/pos/index.html**

找到並修改兩行：

原：
```html
<link rel="stylesheet" href="/static/styles.css">
```
改為：
```html
<link rel="stylesheet" href="/static/shared/styles.css">
```

原：
```html
<script type="module" src="/static/app.js"></script>
```
改為：
```html
<script type="module" src="/static/pos/app.js"></script>
```

- [ ] **Step 2: 更新 frontend/admin/admin.html**

找到並修改：

原：
```html
<link rel="stylesheet" href="/static/styles.css">
```
改為：
```html
<link rel="stylesheet" href="/static/shared/styles.css">
```

原：
```html
<script type="module" src="/static/admin.js"></script>
```
改為：
```html
<script type="module" src="/static/admin/admin.js"></script>
```

- [ ] **Step 3: 更新 main.py 靜態目錄路徑**

找到（約第 40 行）：
```python
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
```
改為：
```python
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
```

- [ ] **Step 4: 更新 backend/routes/core_routes.py 的 FileResponse 路徑**

找到並修改 3 個 FileResponse：

原：
```python
return FileResponse("index.html", headers=_NO_CACHE)
```
改為：
```python
return FileResponse("frontend/pos/index.html", headers=_NO_CACHE)
```

原（出現兩次，`serve_frontend` 和 `serve_pos`）：
兩個都改為 `frontend/pos/index.html`。

原：
```python
return FileResponse("admin.html", headers=_NO_CACHE)
```
改為：
```python
return FileResponse("frontend/admin/admin.html", headers=_NO_CACHE)
```

- [ ] **Step 5: Compile check**

```bash
python3 -m py_compile main.py backend/routes/core_routes.py && echo "OK"
```
期望：OK

- [ ] **Step 6: Commit**

```bash
git add main.py frontend/pos/index.html frontend/admin/admin.html backend/routes/core_routes.py
git commit -m "refactor: update HTML paths, static mount, and FileResponse routes for new structure"
```

---

## Task 5: 最終驗收

- [ ] **Step 1: 確認目錄結構正確**

```bash
echo "=== backend/ ===" && ls backend/
echo "=== frontend/ ===" && ls frontend/
echo "=== frontend/pos/ ===" && ls frontend/pos/
echo "=== frontend/admin/ ===" && ls frontend/admin/
echo "=== frontend/shared/ ===" && ls frontend/shared/
echo "=== root ===" && ls *.py *.txt 2>/dev/null
```

期望：
- `backend/` 有 `ai_services.py`, `database.py`, `routes/`, `services/`, `repositories/`, `realtime/`, `utils/`, `prompts/`
- `frontend/pos/` 有 `index.html`, `app.js`, `cart.js`, `media.js`
- `frontend/admin/` 有 `admin.html`, `admin.js`
- `frontend/shared/` 有 `api.js`, `ui.js`, `media_buffer.js`, `realtime_client.js`, `styles.css`
- 根目錄有 `main.py`, `config.py`
- `static/` 目錄不存在

- [ ] **Step 2: 確認舊路徑已清除**

```bash
# static/ 應不存在
ls static/ 2>&1

# 根目錄應無 Python 業務邏輯檔
ls routes/ services/ repositories/ realtime/ utils/ prompts/ 2>&1

# ai_services.py, database.py 應只在 backend/
ls ai_services.py database.py 2>&1
ls backend/ai_services.py backend/database.py
```

- [ ] **Step 3: 確認 sys.path 設定正確**

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
import ai_services, database
from routes import core_routes
from services import voice_service
print('import OK')
"
```
期望：`import OK`

- [ ] **Step 4: 確認 HTML 路徑更新**

```bash
grep "static/styles\|static/app\|static/admin" frontend/pos/index.html frontend/admin/admin.html
```

期望輸出（`styles.css` 用 shared，JS 用各自目錄）：
```
frontend/pos/index.html:  /static/shared/styles.css
frontend/pos/index.html:  /static/pos/app.js
frontend/admin/admin.html: /static/shared/styles.css
frontend/admin/admin.html: /static/admin/admin.js
```

- [ ] **Step 5: 確認 app.js import 路徑**

```bash
head -25 frontend/pos/app.js | grep "import"
```

期望：
- `api.js` 和 `ui.js` 用 `../shared/`
- `cart.js` 和 `media.js` 用 `./`

- [ ] **Step 6: Full compile check**

```bash
python3 -m py_compile main.py config.py \
  backend/ai_services.py backend/database.py \
  backend/services/voice_service.py backend/services/emotion_service.py \
  backend/services/barrier_state_service.py backend/services/intervention_pipeline_service.py \
  backend/routes/core_routes.py backend/routes/voice_routes.py \
  backend/routes/emotion_routes.py backend/routes/interaction_routes.py \
  backend/routes/menu_routes.py backend/routes/ai_push_routes.py && echo "ALL OK"
```
期望：`ALL OK`

- [ ] **Step 7: 最終 commit**

```bash
git add -A
git commit -m "chore: final verification — directory restructure complete"
```
