# Settings Consolidation Design
**Date:** 2026-06-03  
**Scope:** 將散落在各 `.py` 檔的硬碼常數與 prompt 統一移進 `DEFAULT_SETTINGS` + `settings.json`，順帶修掉兩個已知 Bug。

---

## 目標

- 所有可調整的參數與 prompt 統一由 `config.get()` 讀取
- 後台（`settings.json`）成為唯一真相來源
- 消除 `config.py` 的靜態 `OLLAMA_TIMEOUT` 變數
- 修掉 `_DEFAULT_SYSTEM_PROMPT` NameError 潛伏 Bug
- 修掉 `barrier_state_service.py` 的 typo Bug

---

## 不在範圍內

- `.env` 靜態設定（port、API key、URL）維持原樣
- 連線池（`OLLAMA_POOL_*`）熱重載（需重啟生效，這是預期行為）
- admin UI 介面變動

---

## Section 1：DEFAULT_SETTINGS 新增鍵

檔案：`UI_API/config.py`

### 移除
```python
OLLAMA_TIMEOUT = 120   # 靜態變數，完全移除
```

### 新增進 DEFAULT_SETTINGS
```python
# ── Ollama 連線 ───────────────────────────────
"OLLAMA_TIMEOUT": 120,           # HTTP 請求 timeout（秒），熱改有效
"OLLAMA_POOL_CONNECTIONS": 2,    # 連線池數量，需重啟
"OLLAMA_POOL_MAXSIZE": 4,        # 連線池最大連線數，需重啟

# ── AI 推播 ───────────────────────────────────
"AI_PUSH_PRIORITY_CATS": [       # 優先推播分類，熱改有效
    "超值全餐", "極選系列", "點心", "飲料", "麥當勞分享盒"
],
# AI_PUSH_SYSTEM_PROMPT 已存在，settings.json 中的空字串改為實際 prompt
```

`EMOTION_LLAMA_PROMPT` 已在 DEFAULT_SETTINGS，本次不新增鍵，只修注入邏輯。

---

## Section 2：settings.json 同步

檔案：`UI_API/learning_data/settings.json`

新增以下鍵（與 DEFAULT_SETTINGS 對齊）：
```json
"OLLAMA_TIMEOUT": 120,
"OLLAMA_POOL_CONNECTIONS": 2,
"OLLAMA_POOL_MAXSIZE": 4,
"AI_PUSH_PRIORITY_CATS": ["超值全餐", "極選系列", "點心", "飲料", "麥當勞分享盒"]
```

將現有的 `"AI_PUSH_SYSTEM_PROMPT": ""` 改為實際 prompt 字串（與 DEFAULT_SETTINGS 同步）。

---

## Section 3：各 .py 讀取點修正

### `UI_API/backend/ai_services.py`

**`_get_ollama_session()`**（啟動時讀一次，需重啟）
```python
adapter = HTTPAdapter(
    pool_connections=int(config.get("OLLAMA_POOL_CONNECTIONS", 2)),
    pool_maxsize=int(config.get("OLLAMA_POOL_MAXSIZE", 4)),
)
```

**`_ask_ollama_local()`**（每次呼叫讀，熱改有效）
```python
timeout=int(config.get("OLLAMA_TIMEOUT", 120))
# 取代原本的 config.OLLAMA_TIMEOUT
```

### `UI_API/backend/services/ai_push_service.py`

移除模組頂層常數：
```python
# 刪除
_PRIORITY_CATS = {"超值全餐", "極選系列", "點心", "飲料", "麥當勞分享盒"}
```

`_menu_context()` 改為每次從 config 讀（熱改有效）：
```python
def _menu_context(items: list[dict], limit: int = 80) -> str:
    priority_cats = set(config.get("AI_PUSH_PRIORITY_CATS", []))
    candidates = [i for i in items if i.get("id") and i.get("name")]
    preferred  = [i for i in candidates if str(i.get("category") or "") in priority_cats]
    ...
```

`generate()` 改用 config 讀 system prompt：
```python
system = config.get("AI_PUSH_SYSTEM_PROMPT")
```

### `UI_API/backend/services/voice_service.py`（Bug fix）

移除兩處 `or _DEFAULT_SYSTEM_PROMPT` fallback（定義已刪除，config 有完整預設值）：
```python
system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT_EN")  # 移除 or _DEFAULT_SYSTEM_PROMPT
system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT")     # 移除 or _DEFAULT_SYSTEM_PROMPT
```

### `UI_API/backend/services/barrier_state_service.py`（Bug fix）

修 typo（少了底線導致 menu hesitation dwell timeout 永遠不觸發）：
```python
# 修正前（錯）
or latest_event_type in ("menu_pagedwell_timeout", "category_switch_repeat")
# 修正後（對）
or latest_event_type in ("menu_page_dwell_timeout", "category_switch_repeat")
```

### `UI_API/backend/services/emotion_service.py`

`analyze_event()` 加 `speech_text` 選用參數，讓 prompt 模板可正確注入語音文字：
```python
async def analyze_event(
    session_id: str,
    media_path: str,
    event_type: str,
    speech_text: str = "",
) -> dict:
    prompt_template = config.get("EMOTION_LLAMA_PROMPT", "")
    question = prompt_template.replace("{speech_text}", speech_text)
```

呼叫端（`emotion_routes.py`）傳空字串維持現有行為，介面向下相容。

---

## 變更檔案清單

| 檔案 | 動作 |
|------|------|
| `UI_API/config.py` | 移除靜態 `OLLAMA_TIMEOUT`；DEFAULT_SETTINGS 新增 4 鍵 |
| `UI_API/learning_data/settings.json` | 新增 4 鍵；修 `AI_PUSH_SYSTEM_PROMPT` |
| `UI_API/backend/ai_services.py` | 讀 `OLLAMA_TIMEOUT` / pool 設定改用 `config.get()` |
| `UI_API/backend/services/ai_push_service.py` | 移除 `_PRIORITY_CATS`；讀 config |
| `UI_API/backend/services/voice_service.py` | Bug fix：移除 `_DEFAULT_SYSTEM_PROMPT` 引用 |
| `UI_API/backend/services/barrier_state_service.py` | Bug fix：修 typo |
| `UI_API/backend/services/emotion_service.py` | 加 `speech_text` 參數 |

---

## 行為保證

- 所有預設值與現行行為完全相同（數字/字串不變）
- `OLLAMA_POOL_*` 需重啟生效（在 DEFAULT_SETTINGS 備註說明）
- 其餘設定後台存檔後下次請求即生效（config 熱讀機制不變）
- `emotion_service.analyze_event` 加參數為向下相容（預設空字串）
