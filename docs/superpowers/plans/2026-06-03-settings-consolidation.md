# Settings Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將所有散落在 `.py` 檔的硬碼常數與 prompt 統一移進 `DEFAULT_SETTINGS` + `settings.json`，同時修掉兩個已知 Bug。

**Architecture:** `config.py` 的 `DEFAULT_SETTINGS` 是所有動態參數的唯一真相來源；`settings.json` 是執行期覆蓋層，由後台管理。各 service 一律透過 `config.get("KEY")` 讀取，不再直接宣告模組層級常數。

**Tech Stack:** Python 3.x, FastAPI, `config.get()` 熱讀機制（已有），`python3 -m py_compile` 驗證。

---

## 受影響檔案

| 檔案 | 動作 |
|------|------|
| `UI_API/config.py` | 移除靜態 `OLLAMA_TIMEOUT`；DEFAULT_SETTINGS 新增 4 鍵 |
| `UI_API/learning_data/settings.json` | 新增 4 鍵；修 `AI_PUSH_SYSTEM_PROMPT` 空字串 |
| `UI_API/backend/ai_services.py` | 讀 `OLLAMA_TIMEOUT` / pool 改用 `config.get()` |
| `UI_API/backend/services/ai_push_service.py` | 移除 `_PRIORITY_CATS`；讀 config |
| `UI_API/backend/services/voice_service.py` | Bug fix：移除 `_DEFAULT_SYSTEM_PROMPT` 引用 |
| `UI_API/backend/services/barrier_state_service.py` | Bug fix：修 typo（2 處） |
| `UI_API/backend/services/emotion_service.py` | `analyze_event` 加 `speech_text` 參數 |

---

## Task 1：Bug fix — barrier_state_service.py typo

**Files:**
- Modify: `UI_API/backend/services/barrier_state_service.py:156,165`

- [ ] **Step 1：修正 typo（2 處）**

  開啟 `UI_API/backend/services/barrier_state_service.py`，找到 `"menu_pagedwell_timeout"` 並修正（共兩處，line 156 和 line 165）。

  Line 156（`elif` 條件）：
  ```python
  or latest_event_type in ("menu_page_dwell_timeout", "category_switch_repeat")
  ```

  Line 165（`evidence.append` 的條件）：
  ```python
  if latest_event_type in ("menu_page_dwell_timeout", "category_switch_repeat"):
  ```

- [ ] **Step 2：驗證語法**

  ```bash
  cd UI_API && python3 -m py_compile backend/services/barrier_state_service.py && echo OK
  ```
  Expected: `OK`

- [ ] **Step 3：Commit**

  ```bash
  git add UI_API/backend/services/barrier_state_service.py
  git commit -m "fix: restore menu_page_dwell_timeout typo in barrier_state_service"
  ```

---

## Task 2：Bug fix — voice_service.py NameError

**Files:**
- Modify: `UI_API/backend/services/voice_service.py:87,89`

- [ ] **Step 1：移除 `or _DEFAULT_SYSTEM_PROMPT` 兩處**

  `UI_API/backend/services/voice_service.py` lines 86-89，改為：
  ```python
  if detected_lang == "en":
      system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT_EN")
  else:
      system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT")
  ```

- [ ] **Step 2：驗證語法**

  ```bash
  cd UI_API && python3 -m py_compile backend/services/voice_service.py && echo OK
  ```
  Expected: `OK`

- [ ] **Step 3：Commit**

  ```bash
  git add UI_API/backend/services/voice_service.py
  git commit -m "fix: remove dangling _DEFAULT_SYSTEM_PROMPT reference in voice_service"
  ```

---

## Task 3：config.py — 移除靜態 OLLAMA_TIMEOUT，新增 4 鍵至 DEFAULT_SETTINGS

**Files:**
- Modify: `UI_API/config.py:42` (移除), `UI_API/config.py:DEFAULT_SETTINGS` (新增)

- [ ] **Step 1：移除靜態 `OLLAMA_TIMEOUT` 變數**

  刪除 `UI_API/config.py` 第 42 行整行：
  ```python
  # 刪除這行
  OLLAMA_TIMEOUT = 120
  ```

- [ ] **Step 2：在 DEFAULT_SETTINGS 新增 4 個鍵**

  在 `OLLAMA_LOG_RAW` 那行之後（目前 line 63）插入 Ollama 連線區塊，並在 AI 推播區塊加入 `AI_PUSH_PRIORITY_CATS`：

  Ollama 連線設定（插入在 `"OLLAMA_LOG_RAW": False,` 之後）：
  ```python
  "OLLAMA_LOG_RAW": False,
  "OLLAMA_TIMEOUT": 120,           # HTTP 請求 timeout（秒），熱改有效
  "OLLAMA_POOL_CONNECTIONS": 2,    # 連線池數量（需重啟生效）
  "OLLAMA_POOL_MAXSIZE": 4,        # 連線池最大連線數（需重啟生效）
  ```

  AI 推播優先分類（插入在 `"CHOICE_HESITATION_IDLE_SEC": 60,` 之後）：
  ```python
  "CHOICE_HESITATION_IDLE_SEC": 60,       # 無操作多少秒後顯示猶豫彈窗
  "AI_PUSH_PRIORITY_CATS": [              # 優先推播分類，熱改有效
      "超值全餐", "極選系列", "點心", "飲料", "麥當勞分享盒"
  ],
  ```

- [ ] **Step 3：驗證語法與 config.get 回傳值**

  ```bash
  cd UI_API && python3 -m py_compile config.py && echo OK
  ```
  Expected: `OK`

  ```bash
  cd UI_API && python3 -c "
  import config
  assert config.get('OLLAMA_TIMEOUT') == 120, config.get('OLLAMA_TIMEOUT')
  assert config.get('OLLAMA_POOL_CONNECTIONS') == 2
  assert config.get('OLLAMA_POOL_MAXSIZE') == 4
  assert config.get('AI_PUSH_PRIORITY_CATS') == ['超值全餐','極選系列','點心','飲料','麥當勞分享盒']
  print('config assertions OK')
  "
  ```
  Expected: `config assertions OK`

  確認舊的靜態屬性已不存在：
  ```bash
  cd UI_API && python3 -c "import config; print(hasattr(config, 'OLLAMA_TIMEOUT'))"
  ```
  Expected: `False`

- [ ] **Step 4：Commit**

  ```bash
  git add UI_API/config.py
  git commit -m "feat: move OLLAMA_TIMEOUT and pool/push-cats settings into DEFAULT_SETTINGS"
  ```

---

## Task 4：settings.json — 同步新鍵，修正 AI_PUSH_SYSTEM_PROMPT

**Files:**
- Modify: `UI_API/learning_data/settings.json`

- [ ] **Step 1：修正 `AI_PUSH_SYSTEM_PROMPT` 空字串**

  `UI_API/learning_data/settings.json` line 22，將：
  ```json
  "AI_PUSH_SYSTEM_PROMPT": "",
  ```
  改為：
  ```json
  "AI_PUSH_SYSTEM_PROMPT": "你是麥當勞自助點餐機的 AI 推播助手。只能從菜單白名單選 1 個餐點，不能發明不存在的餐點。輸出純 JSON：{\"recommendation_id\":\"MCDxxx\",\"push_text\":\"繁體中文促購短句\"}。",
  ```

- [ ] **Step 2：在 `BARRIER_PAYMENT_FAIL_MAX` 之後新增 4 個鍵**

  在 `"BARRIER_PAYMENT_FAIL_MAX": 1,` 之後插入：
  ```json
  "OLLAMA_TIMEOUT": 120,
  "OLLAMA_POOL_CONNECTIONS": 2,
  "OLLAMA_POOL_MAXSIZE": 4,
  "AI_PUSH_PRIORITY_CATS": ["超值全餐", "極選系列", "點心", "飲料", "麥當勞分享盒"],
  ```

- [ ] **Step 3：驗證 JSON 格式**

  ```bash
  cd UI_API && python3 -c "import json; json.load(open('learning_data/settings.json')); print('JSON OK')"
  ```
  Expected: `JSON OK`

  確認 `AI_PUSH_SYSTEM_PROMPT` 不再是空字串：
  ```bash
  cd UI_API && python3 -c "
  import json
  s = json.load(open('learning_data/settings.json'))
  assert s['AI_PUSH_SYSTEM_PROMPT'] != '', 'still empty!'
  assert s['OLLAMA_TIMEOUT'] == 120
  assert s['AI_PUSH_PRIORITY_CATS'] == ['超值全餐','極選系列','點心','飲料','麥當勞分享盒']
  print('settings.json assertions OK')
  "
  ```
  Expected: `settings.json assertions OK`

- [ ] **Step 4：Commit**

  ```bash
  git add UI_API/learning_data/settings.json
  git commit -m "feat: sync settings.json with new DEFAULT_SETTINGS keys"
  ```

---

## Task 5：ai_services.py — 讀 pool / timeout 改用 config.get()

**Files:**
- Modify: `UI_API/backend/ai_services.py:18` (pool), `UI_API/backend/ai_services.py:257` (timeout)

- [ ] **Step 1：`_get_ollama_session()` 改讀 config**

  `UI_API/backend/ai_services.py` lines 17-21，改為：
  ```python
  def _get_ollama_session() -> requests.Session:
      global _ollama_session
      if _ollama_session is None:
          s = requests.Session()
          adapter = HTTPAdapter(
              pool_connections=int(config.get("OLLAMA_POOL_CONNECTIONS", 2)),
              pool_maxsize=int(config.get("OLLAMA_POOL_MAXSIZE", 4)),
          )
          s.mount("http://", adapter)
          s.mount("https://", adapter)
          _ollama_session = s
      return _ollama_session
  ```

- [ ] **Step 2：`_ask_ollama_local()` timeout 改讀 config**

  `UI_API/backend/ai_services.py` line 257，將：
  ```python
  response = _get_ollama_session().post(config.OLLAMA_API_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
  ```
  改為：
  ```python
  response = _get_ollama_session().post(config.OLLAMA_API_URL, json=payload, timeout=int(config.get("OLLAMA_TIMEOUT", 120)))
  ```

- [ ] **Step 3：驗證語法**

  ```bash
  cd UI_API && python3 -m py_compile backend/ai_services.py && echo OK
  ```
  Expected: `OK`

  確認 `config.OLLAMA_TIMEOUT` 已無任何引用：
  ```bash
  grep -n "config\.OLLAMA_TIMEOUT" UI_API/backend/ai_services.py
  ```
  Expected: 無輸出

- [ ] **Step 4：Commit**

  ```bash
  git add UI_API/backend/ai_services.py
  git commit -m "feat: read OLLAMA_TIMEOUT and pool settings from config.get() in ai_services"
  ```

---

## Task 6：ai_push_service.py — 移除 _PRIORITY_CATS，讀 config

**Files:**
- Modify: `UI_API/backend/services/ai_push_service.py:10,22,66-70`

- [ ] **Step 1：移除模組層級 `_PRIORITY_CATS` 常數**

  刪除 `UI_API/backend/services/ai_push_service.py` 第 10 行：
  ```python
  # 刪除這行
  _PRIORITY_CATS = {"超值全餐", "極選系列", "點心", "飲料", "麥當勞分享盒"}
  ```

- [ ] **Step 2：`_menu_context()` 改從 config 讀**

  `UI_API/backend/services/ai_push_service.py` 的 `_menu_context` 函式，在函式開頭加入 config 讀取，原本使用 `_PRIORITY_CATS` 的行改用區域變數：

  ```python
  def _menu_context(items: list[dict], limit: int = 80) -> str:
      priority_cats = set(config.get("AI_PUSH_PRIORITY_CATS", []))
      candidates = [i for i in items if i.get("id") and i.get("name")]
      preferred  = [i for i in candidates if str(i.get("category") or "") in priority_cats]
      rows = [
          f"{i['id']}｜{i['name']}｜{i.get('category', '')}｜${_price(i)}"
          for i in (preferred or candidates)[:limit]
      ]
      return "\n".join(rows)
  ```

- [ ] **Step 3：`generate()` 改讀 system prompt**

  `UI_API/backend/services/ai_push_service.py` 的 `generate()` 函式，找到硬碼的 `system = (...)` 區塊（約 lines 66-70），整個替換為一行：
  ```python
  system = config.get("AI_PUSH_SYSTEM_PROMPT")
  ```

- [ ] **Step 4：驗證語法與 _PRIORITY_CATS 已消除**

  ```bash
  cd UI_API && python3 -m py_compile backend/services/ai_push_service.py && echo OK
  ```
  Expected: `OK`

  ```bash
  grep -n "_PRIORITY_CATS" UI_API/backend/services/ai_push_service.py
  ```
  Expected: 無輸出

- [ ] **Step 5：Commit**

  ```bash
  git add UI_API/backend/services/ai_push_service.py
  git commit -m "feat: read AI_PUSH_PRIORITY_CATS and system prompt from config in ai_push_service"
  ```

---

## Task 7：emotion_service.py — analyze_event 加 speech_text 參數

**Files:**
- Modify: `UI_API/backend/services/emotion_service.py:49,56`

- [ ] **Step 1：`analyze_event` 函式簽名加 `speech_text` 參數**

  `UI_API/backend/services/emotion_service.py` line 49，將：
  ```python
  async def analyze_event(session_id: str, media_path: str, event_type: str) -> dict:
  ```
  改為：
  ```python
  async def analyze_event(session_id: str, media_path: str, event_type: str, speech_text: str = "") -> dict:
  ```

- [ ] **Step 2：注入 speech_text 至 prompt 模板**

  同檔案 line 56（`question = prompt_template.replace(...)`），將：
  ```python
  question = prompt_template.replace("{speech_text}", "")
  ```
  改為：
  ```python
  question = prompt_template.replace("{speech_text}", speech_text)
  ```

- [ ] **Step 3：驗證語法**

  ```bash
  cd UI_API && python3 -m py_compile backend/services/emotion_service.py && echo OK
  ```
  Expected: `OK`

  確認呼叫端 `emotion_routes.py` 不需要修改（`speech_text=""` 是預設值，向下相容）：
  ```bash
  cd UI_API && python3 -m py_compile backend/routes/emotion_routes.py && echo OK
  ```
  Expected: `OK`

- [ ] **Step 4：Commit**

  ```bash
  git add UI_API/backend/services/emotion_service.py
  git commit -m "feat: add optional speech_text param to analyze_event for EMOTION_LLAMA_PROMPT injection"
  ```

---

## 最終驗證

- [ ] **全檔語法掃描**

  ```bash
  cd UI_API && for f in config.py backend/ai_services.py backend/services/ai_push_service.py backend/services/voice_service.py backend/services/barrier_state_service.py backend/services/emotion_service.py; do python3 -m py_compile $f && echo "$f OK"; done
  ```
  Expected: 每行都印 `OK`

- [ ] **確認舊靜態屬性已消除**

  ```bash
  cd UI_API && python3 -c "import config; print(hasattr(config, 'OLLAMA_TIMEOUT'))"
  ```
  Expected: `False`

- [ ] **確認 config.get 能讀到全部新鍵**

  ```bash
  cd UI_API && python3 -c "
  import config
  keys = ['OLLAMA_TIMEOUT','OLLAMA_POOL_CONNECTIONS','OLLAMA_POOL_MAXSIZE','AI_PUSH_PRIORITY_CATS','AI_PUSH_SYSTEM_PROMPT']
  for k in keys:
      v = config.get(k)
      assert v is not None and v != '', f'{k} missing or empty'
      print(f'{k}: {str(v)[:60]}')
  "
  ```
  Expected: 5 行各顯示 key 與值，無 AssertionError

- [ ] **確認 `_PRIORITY_CATS` 與 `_DEFAULT_SYSTEM_PROMPT` 已消除**

  ```bash
  grep -rn "_PRIORITY_CATS\|_DEFAULT_SYSTEM_PROMPT" UI_API/backend/
  ```
  Expected: 無輸出

- [ ] **確認 barrier typo 已修正**

  ```bash
  grep -n "menu_pagedwell_timeout" UI_API/backend/services/barrier_state_service.py
  ```
  Expected: 無輸出
