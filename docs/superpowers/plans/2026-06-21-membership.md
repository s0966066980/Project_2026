# 會員制（Membership）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 kiosk 點餐入口加入「會員點餐／直接點餐」選擇，會員以手機號碼登入或快速註冊，歷史點餐紀錄驅動個人化推薦（您的常點 + 推播加權 + LLM context），後台新增會員列表/詳情。

**Architecture:** 後端依既有分層新增 `member_repository`（JSON store）→ `member_service`（業務邏輯 + session↔會員記憶體綁定）→ `member_routes`（POS 登入/註冊公開、admin 列表/詳情）。個人化在 `ai_push_service` 與 `checkout_service` 既有流程上以 `session_id` 反查會員疊加。前端新增 `member.js` 模組與三個 overlay，`startBtn` 流程改為先出選擇頁。

**Tech Stack:** Python 3 / FastAPI、pytest 9（conda env `emotion_ui`）、Vanilla JS ES modules（無 bundler、無 JS 測試框架，以 `node --check` + 人工瀏覽器驗證）。

## Global Constraints

- 分層：routes 只解析請求 + 呼叫 service；service 不直接讀寫 JSON（透過 repository）；repository 不放業務邏輯、不做 AI 呼叫。
- 菜單白名單：所有顯示/推薦品項來自 `menu.json`（MCDxxx），LLM 不得幻覺餐點。
- XSS：會員暱稱與品名 render 進 DOM 一律用 `textContent` / `escapeHTML`，禁止 innerHTML 直插。
- 隱私：kiosk 顯示完整手機號碼；後台一律遮罩中間碼 `0912-***-678`。
- 讀設定統一 `config.get("KEY")`；POS 需讀的 key 加入 `PUBLIC_SETTINGS_KEYS`。
- 不在 checkout 加阻擋邏輯：會員紀錄更新是結帳成功後的附帶副作用，任何失敗都不得阻擋結帳回應。
- 功能開關 `MEMBER_ENABLED=false` 時 kiosk 跳過選擇頁（等同現狀）、後台分頁隱藏。
- `item_freq` 以「光臨次數」累積：每次結帳對去重後的 `final_cart_ids` 中每個 id +1。
- 訂單 total 不可由 `cart_ids` 反推（id 已去重），由前端 `cart_total` 帶入。
- ES module：跨模組 import 只在函式體內解參，沿用 state.js / 循環 import 慣例。
- 測試執行根目錄：`/home/oliver/Project_2026/UI_API`，指令前綴 `conda run -n emotion_ui python -m pytest`。

---

### Task 1: 測試骨架 + member_repository

**Files:**
- Create: `UI_API/conftest.py`
- Create: `UI_API/backend/repositories/member_repository.py`
- Test: `UI_API/tests/test_member_repository.py`

**Interfaces:**
- Produces:
  - `member_repository.MEMBERS_PATH: str`（模組全域，測試可 monkeypatch）
  - `member_repository.get_all_members() -> list`
  - `member_repository.get_member(phone: str) -> dict | None`
  - `member_repository.upsert_member(record: dict) -> dict`（以 `record["phone"]` 比對，存在則取代、不存在則 append）

- [ ] **Step 1: 建立 pytest 路徑設定**

`UI_API/conftest.py`（讓測試能 `import config` 與 `from repositories/services import ...`）：

```python
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_ROOT, "backend")
for _p in (_ROOT, _BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)
```

- [ ] **Step 2: 寫失敗測試**

`UI_API/tests/test_member_repository.py`：

```python
import os
import importlib

import pytest


@pytest.fixture
def repo(tmp_path, monkeypatch):
    from repositories import member_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    return member_repository


def _rec(phone, nickname="x"):
    return {"phone": phone, "nickname": nickname, "visit_count": 0, "item_freq": {}, "orders": []}


def test_missing_file_returns_empty(repo):
    assert repo.get_all_members() == []
    assert repo.get_member("0912345678") is None


def test_upsert_then_get(repo):
    repo.upsert_member(_rec("0912345678", "小明"))
    got = repo.get_member("0912345678")
    assert got["nickname"] == "小明"
    assert repo.get_all_members() and len(repo.get_all_members()) == 1


def test_upsert_replaces_same_phone(repo):
    repo.upsert_member(_rec("0912345678", "舊"))
    repo.upsert_member(_rec("0912345678", "新"))
    assert len(repo.get_all_members()) == 1
    assert repo.get_member("0912345678")["nickname"] == "新"


def test_upsert_appends_distinct_phone(repo):
    repo.upsert_member(_rec("0912345678"))
    repo.upsert_member(_rec("0928000000"))
    assert len(repo.get_all_members()) == 2
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_repository.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'repositories.member_repository'`）

- [ ] **Step 4: 實作 member_repository**

`UI_API/backend/repositories/member_repository.py`（沿用 `log_repository` 的 atomic write 風格）：

```python
import json
import os
import threading

import config

MEMBERS_PATH = os.path.join(config.LEARNING_DATA_DIR, "members.json")

_lock = threading.Lock()


def _read() -> list:
    try:
        with open(MEMBERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(rows: list) -> list:
    parent = os.path.dirname(MEMBERS_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f"{MEMBERS_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, MEMBERS_PATH)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return rows


def get_all_members() -> list:
    with _lock:
        return _read()


def get_member(phone: str) -> dict | None:
    key = str(phone or "")
    with _lock:
        for row in _read():
            if str(row.get("phone")) == key:
                return row
    return None


def upsert_member(record: dict) -> dict:
    key = str(record.get("phone") or "")
    with _lock:
        rows = _read()
        for i, row in enumerate(rows):
            if str(row.get("phone")) == key:
                rows[i] = record
                break
        else:
            rows.append(record)
        _write(rows)
    return record
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_repository.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/conftest.py UI_API/backend/repositories/member_repository.py UI_API/tests/test_member_repository.py
git commit -m "feat(member): add member_repository JSON store + pytest scaffolding"
```

---

### Task 2: member_service 核心（手機工具 + 登入/註冊 + session 綁定）

**Files:**
- Create: `UI_API/backend/services/member_service.py`
- Test: `UI_API/tests/test_member_service_core.py`

**Interfaces:**
- Consumes: `member_repository.get_member/upsert_member`
- Produces:
  - `normalize_phone(raw) -> str`（10 碼數字否則回 `""`）
  - `mask_phone(phone) -> str`（`0912-***-678`）
  - `bind_session(session_id, phone)` / `get_session_member(session_id) -> dict | None` / `clear_session(session_id)`
  - `login(session_id, phone) -> dict`：`{"found": bool, "member"?: {...}, "error"?: "invalid_phone"}`
  - `register(session_id, phone, nickname="") -> dict`：`{"ok": bool, "member"?: {...}, "error"?: "invalid_phone"}`
  - `_public_member(member) -> dict`：`{"phone","nickname","visit_count","usuals"}`（`usuals` 由 Task 3 的 `build_usuals` 提供；本任務先以空 list 佔位，Task 3 接上）

**Note:** 本任務 `_public_member` 暫不含 usuals 計算（Task 3 補），先回 `"usuals": []`，避免跨任務依賴未完成函式。

- [ ] **Step 1: 寫失敗測試**

`UI_API/tests/test_member_service_core.py`：

```python
import importlib

import pytest


@pytest.fixture
def svc(tmp_path, monkeypatch):
    from repositories import member_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    from services import member_service
    importlib.reload(member_service)
    member_service._session_member.clear()
    return member_service


def test_normalize_phone(svc):
    assert svc.normalize_phone("0912-345-678") == "0912345678"
    assert svc.normalize_phone(" 0912345678 ") == "0912345678"
    assert svc.normalize_phone("12345") == ""
    assert svc.normalize_phone(None) == ""


def test_mask_phone(svc):
    assert svc.mask_phone("0912345678") == "0912-***-678"
    assert svc.mask_phone("xyz") == "xyz"


def test_login_not_found(svc):
    assert svc.login("s1", "0912345678") == {"found": False}


def test_login_invalid_phone(svc):
    assert svc.login("s1", "999")["found"] is False
    assert svc.login("s1", "999")["error"] == "invalid_phone"


def test_register_then_login_binds_session(svc):
    reg = svc.register("s1", "0912-345-678", "小明")
    assert reg["ok"] is True
    assert reg["member"]["nickname"] == "小明"
    assert svc.get_session_member("s1")["phone"] == "0912345678"
    out = svc.login("s2", "0912345678")
    assert out["found"] is True
    assert svc.get_session_member("s2")["phone"] == "0912345678"


def test_register_default_nickname(svc):
    reg = svc.register("s1", "0955000321", "")
    assert reg["member"]["nickname"] == "會員0321"


def test_clear_session(svc):
    svc.register("s1", "0912345678", "小明")
    svc.clear_session("s1")
    assert svc.get_session_member("s1") is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_service_core.py -v`
Expected: FAIL（`No module named 'services.member_service'`）

- [ ] **Step 3: 實作 member_service（核心部分）**

`UI_API/backend/services/member_service.py`：

```python
import re
import threading
from datetime import datetime

import config
from repositories import member_repository, menu_repository

_session_member: dict[str, str] = {}
_lock = threading.Lock()


def normalize_phone(raw) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits if len(digits) == 10 else ""


def mask_phone(phone) -> str:
    p = str(phone or "")
    if len(p) != 10:
        return p
    return f"{p[:4]}-***-{p[7:]}"


def bind_session(session_id: str, phone: str) -> None:
    with _lock:
        _session_member[session_id] = phone


def clear_session(session_id: str) -> None:
    with _lock:
        _session_member.pop(session_id, None)


def get_session_member(session_id: str) -> dict | None:
    phone = _session_member.get(session_id)
    return member_repository.get_member(phone) if phone else None


def _public_member(member: dict) -> dict:
    return {
        "phone": member.get("phone", ""),
        "nickname": member.get("nickname", ""),
        "visit_count": int(member.get("visit_count", 0)),
        "usuals": build_usuals(member),
    }


def login(session_id: str, phone: str) -> dict:
    norm = normalize_phone(phone)
    if not norm:
        return {"found": False, "error": "invalid_phone"}
    member = member_repository.get_member(norm)
    if not member:
        return {"found": False}
    bind_session(session_id, norm)
    return {"found": True, "member": _public_member(member)}


def register(session_id: str, phone: str, nickname: str = "") -> dict:
    norm = normalize_phone(phone)
    if not norm:
        return {"ok": False, "error": "invalid_phone"}
    existing = member_repository.get_member(norm)
    if existing:
        bind_session(session_id, norm)
        return {"ok": True, "member": _public_member(existing)}
    nick = str(nickname or "").strip() or f"會員{norm[-4:]}"
    record = {
        "phone": norm,
        "nickname": nick,
        "created_at": datetime.now().isoformat(),
        "visit_count": 0,
        "total_spend": 0,
        "last_visit_at": "",
        "item_freq": {},
        "orders": [],
    }
    member_repository.upsert_member(record)
    bind_session(session_id, norm)
    return {"ok": True, "member": _public_member(record)}


def build_usuals(member: dict, limit: int | None = None) -> list:
    # Task 3 取代此實作；核心任務先回空 list 以滿足 _public_member。
    return []
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_service_core.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/backend/services/member_service.py UI_API/tests/test_member_service_core.py
git commit -m "feat(member): member_service phone utils, login/register, session binding"
```

---

### Task 3: member_service 個人化（build_usuals / member_push_context / member_top_ids / finalize_checkout）

**Files:**
- Modify: `UI_API/backend/services/member_service.py`
- Test: `UI_API/tests/test_member_service_personalization.py`

**Interfaces:**
- Consumes: `menu_repository.get_menu`、`config.get`
- Produces:
  - `build_usuals(member, limit=None) -> list`：依 `item_freq` 排序、join 菜單（白名單）、回 `[{id,name,price,image,category,count}]`，預設上限 `config.get("MEMBER_USUALS_COUNT", 8)`
  - `member_top_ids(member, n=5) -> list[str]`：item_freq 前 n 名 id
  - `member_push_context(member) -> str`：LLM 注入字串（無常點回 `""`）
  - `finalize_checkout(session_id, final_cart_ids, total, is_success) -> dict | None`：更新 visit/spend/last_visit/item_freq/orders（orders 上限 `config.get("MEMBER_ORDERS_KEEP", 20)`），清除綁定，回更新後的 member；session 無綁定回 None

- [ ] **Step 1: 寫失敗測試**

`UI_API/tests/test_member_service_personalization.py`：

```python
import importlib

import pytest


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐", "official_image_url": "/x.jpg"},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
    {"id": "MCD030", "name": "可口可樂(中)", "price": 35, "category": "飲料"},
]


@pytest.fixture
def svc(tmp_path, monkeypatch):
    from repositories import member_repository, menu_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    monkeypatch.setattr(menu_repository, "get_menu", lambda: list(MENU))
    from services import member_service
    importlib.reload(member_service)
    member_service._session_member.clear()
    monkeypatch.setattr(member_service.menu_repository, "get_menu", lambda: list(MENU))
    return member_service


def _member(freq):
    return {"phone": "0912345678", "nickname": "小明", "visit_count": 3,
            "total_spend": 600, "item_freq": dict(freq), "orders": []}


def test_build_usuals_sorted_and_whitelisted(svc):
    m = _member({"MCD012": 6, "MCD001": 8, "MCD999": 99})  # MCD999 不在菜單 → 過濾
    usuals = svc.build_usuals(m)
    assert [u["id"] for u in usuals] == ["MCD001", "MCD012"]
    assert usuals[0]["count"] == 8
    assert usuals[0]["image"] == "/x.jpg"
    assert usuals[0]["name"] == "大麥克套餐"


def test_build_usuals_respects_limit(svc):
    m = _member({"MCD001": 8, "MCD012": 6, "MCD030": 5})
    assert len(svc.build_usuals(m, limit=2)) == 2


def test_member_top_ids(svc):
    m = _member({"MCD001": 8, "MCD012": 6, "MCD030": 5})
    assert svc.member_top_ids(m, 2) == ["MCD001", "MCD012"]


def test_member_push_context(svc):
    m = _member({"MCD001": 8})
    ctx = svc.member_push_context(m)
    assert "大麥克套餐" in ctx and "小明" in ctx
    assert svc.member_push_context(_member({})) == ""


def test_finalize_checkout_updates_profile(svc):
    svc.register("s1", "0912345678", "小明")
    out = svc.finalize_checkout("s1", ["MCD001", "MCD012", "MCD001"], 200, True)
    assert out["visit_count"] == 1
    assert out["total_spend"] == 200
    # 去重 → 光臨次數：MCD001 與 MCD012 各 +1
    assert out["item_freq"] == {"MCD001": 1, "MCD012": 1}
    assert len(out["orders"]) == 1 and out["orders"][0]["total"] == 200
    assert svc.get_session_member("s1") is None  # 綁定已清除


def test_finalize_checkout_no_member_returns_none(svc):
    assert svc.finalize_checkout("nobody", ["MCD001"], 100, True) is None


def test_finalize_checkout_orders_capped(svc, monkeypatch):
    monkeypatch.setattr(svc.config, "get", lambda k, d=None: 2 if k == "MEMBER_ORDERS_KEEP" else d)
    svc.register("s1", "0912345678", "小明")
    for _ in range(3):
        svc.bind_session("s1", "0912345678")
        svc.finalize_checkout("s1", ["MCD001"], 100, True)
    m = svc.member_repository.get_member("0912345678")
    assert len(m["orders"]) == 2
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_service_personalization.py -v`
Expected: FAIL（`build_usuals` 回空 list、`member_top_ids`/`finalize_checkout` 未定義）

- [ ] **Step 3: 取代 build_usuals 並新增函式**

把 Task 2 的 `build_usuals` 佔位實作整段取代為下列，並在檔尾新增其餘函式：

```python
def build_usuals(member: dict, limit: int | None = None) -> list:
    if limit is None:
        limit = int(config.get("MEMBER_USUALS_COUNT", 8))
    freq = member.get("item_freq") or {}
    if not freq:
        return []
    menu_by_id = {i["id"]: i for i in menu_repository.get_menu() if i.get("id")}
    usuals = []
    for iid, count in sorted(freq.items(), key=lambda kv: kv[1], reverse=True):
        item = menu_by_id.get(iid)
        if not item:
            continue
        usuals.append({
            "id": iid,
            "name": item.get("name", ""),
            "price": item.get("price", 0),
            "image": item.get("official_image_url") or item.get("image", ""),
            "category": item.get("category", ""),
            "count": count,
        })
        if len(usuals) >= limit:
            break
    return usuals


def member_top_ids(member: dict, n: int = 5) -> list:
    freq = member.get("item_freq") or {}
    return [iid for iid, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:n]]


def member_push_context(member: dict) -> str:
    usuals = build_usuals(member, limit=3)
    names = "、".join(u["name"] for u in usuals if u.get("name"))
    if not names:
        return ""
    nick = member.get("nickname", "")
    who = f"「{nick}」" if nick else ""
    return f"此顧客為會員{who}，常點：{names}。請在促購短句中自然帶入其偏好。"


def finalize_checkout(session_id: str, final_cart_ids: list, total, is_success: bool) -> dict | None:
    member = get_session_member(session_id)
    if not member:
        clear_session(session_id)
        return None
    member["visit_count"] = int(member.get("visit_count", 0)) + 1
    member["total_spend"] = int(member.get("total_spend", 0)) + int(total or 0)
    member["last_visit_at"] = datetime.now().isoformat()
    freq = dict(member.get("item_freq") or {})
    for iid in set(final_cart_ids or []):
        if iid:
            freq[iid] = freq.get(iid, 0) + 1
    member["item_freq"] = freq
    orders = list(member.get("orders") or [])
    orders.append({
        "timestamp": datetime.now().isoformat(),
        "cart_ids": list(final_cart_ids or []),
        "total": int(total or 0),
        "is_success": bool(is_success),
    })
    keep = int(config.get("MEMBER_ORDERS_KEEP", 20))
    member["orders"] = orders[-keep:]
    member_repository.upsert_member(member)
    clear_session(session_id)
    return member
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_service_personalization.py tests/test_member_service_core.py -v`
Expected: PASS（core 的 `test_register_then_login_binds_session` 仍綠，因 `_public_member` 現在回真實 usuals；register 後 item_freq 為空 → usuals=[]）

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/backend/services/member_service.py UI_API/tests/test_member_service_personalization.py
git commit -m "feat(member): usuals, push context, finalize_checkout profile update"
```

---

### Task 4: member_service 後台聚合（admin_list / admin_detail）

**Files:**
- Modify: `UI_API/backend/services/member_service.py`
- Test: `UI_API/tests/test_member_service_admin.py`

**Interfaces:**
- Produces:
  - `admin_list() -> list`：`[{phone_masked, phone, nickname, visit_count, total_spend, last_visit_at, favorites:[name,...]}]`（favorites = top 2 常點品名）
  - `admin_detail(phone) -> dict | None`：`{phone_masked, nickname, created_at, visit_count, total_spend, avg_spend, last_visit_at, favorites_ranked:[{id,name,count}], orders:[最新在前]}`

- [ ] **Step 1: 寫失敗測試**

`UI_API/tests/test_member_service_admin.py`：

```python
import importlib

import pytest


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155},
    {"id": "MCD012", "name": "薯條(中)", "price": 45},
]


@pytest.fixture
def svc(tmp_path, monkeypatch):
    from repositories import member_repository, menu_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    monkeypatch.setattr(menu_repository, "get_menu", lambda: list(MENU))
    from services import member_service
    importlib.reload(member_service)
    member_service._session_member.clear()
    monkeypatch.setattr(member_service.menu_repository, "get_menu", lambda: list(MENU))
    return member_service


def _seed(svc, phone, nick, freq, visit, spend):
    svc.member_repository.upsert_member({
        "phone": phone, "nickname": nick, "created_at": "2026-03-01T00:00:00",
        "visit_count": visit, "total_spend": spend, "last_visit_at": "2026-06-20T00:00:00",
        "item_freq": dict(freq),
        "orders": [{"timestamp": "2026-06-20T00:00:00", "cart_ids": list(freq), "total": spend, "is_success": True}],
    })


def test_admin_list(svc):
    _seed(svc, "0912345678", "小明", {"MCD001": 8, "MCD012": 6}, 12, 3720)
    rows = svc.admin_list()
    assert len(rows) == 1
    r = rows[0]
    assert r["phone_masked"] == "0912-***-678"
    assert r["nickname"] == "小明"
    assert r["favorites"] == ["大麥克套餐", "薯條(中)"]


def test_admin_detail(svc):
    _seed(svc, "0912345678", "小明", {"MCD001": 8, "MCD012": 6}, 12, 3720)
    d = svc.admin_detail("0912345678")
    assert d["phone_masked"] == "0912-***-678"
    assert d["avg_spend"] == 310  # 3720 // 12
    assert d["favorites_ranked"][0] == {"id": "MCD001", "name": "大麥克套餐", "count": 8}
    assert len(d["orders"]) == 1


def test_admin_detail_missing(svc):
    assert svc.admin_detail("0900000000") is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_service_admin.py -v`
Expected: FAIL（`admin_list`/`admin_detail` 未定義）

- [ ] **Step 3: 新增後台聚合函式（檔尾）**

```python
def admin_list() -> list:
    members = member_repository.get_all_members()
    menu_by_id = {i["id"]: i for i in menu_repository.get_menu() if i.get("id")}
    rows = []
    for m in members:
        favs = [menu_by_id.get(iid, {}).get("name", iid) for iid in member_top_ids(m, 2)]
        rows.append({
            "phone_masked": mask_phone(m.get("phone", "")),
            "phone": m.get("phone", ""),
            "nickname": m.get("nickname", ""),
            "visit_count": int(m.get("visit_count", 0)),
            "total_spend": int(m.get("total_spend", 0)),
            "last_visit_at": m.get("last_visit_at", ""),
            "favorites": favs,
        })
    return rows


def admin_detail(phone) -> dict | None:
    m = member_repository.get_member(normalize_phone(phone) or str(phone))
    if not m:
        return None
    menu_by_id = {i["id"]: i for i in menu_repository.get_menu() if i.get("id")}
    freq = m.get("item_freq") or {}
    ranked = [
        {"id": iid, "name": menu_by_id.get(iid, {}).get("name", iid), "count": cnt}
        for iid, cnt in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    ]
    visit = int(m.get("visit_count", 0))
    spend = int(m.get("total_spend", 0))
    return {
        "phone_masked": mask_phone(m.get("phone", "")),
        "nickname": m.get("nickname", ""),
        "created_at": m.get("created_at", ""),
        "visit_count": visit,
        "total_spend": spend,
        "avg_spend": (spend // visit if visit else 0),
        "last_visit_at": m.get("last_visit_at", ""),
        "favorites_ranked": ranked,
        "orders": list(reversed(m.get("orders") or [])),
    }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_service_admin.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/backend/services/member_service.py UI_API/tests/test_member_service_admin.py
git commit -m "feat(member): admin_list and admin_detail aggregation"
```

---

### Task 5: 設定 MEMBER_* + member_routes + main.py 掛載

**Files:**
- Modify: `UI_API/config.py`（`DEFAULT_SETTINGS` 與 `PUBLIC_SETTINGS_KEYS`）
- Create: `UI_API/backend/routes/member_routes.py`
- Modify: `UI_API/main.py:15-27`（import）、`:168-180`（include_router）
- Test: `UI_API/tests/test_member_routes.py`

**Interfaces:**
- Consumes: `member_service.login/register/admin_list/admin_detail`
- Produces（POS）：`POST /api/member/login`、`POST /api/member/register`；（admin）：`GET /api/members`、`GET /api/members/{phone}`
- `member_routes.create_router(deps: dict) -> APIRouter`（沿用既有 pattern；本路由不使用 deps）

- [ ] **Step 1: 新增設定 key**

`config.py` 的 `DEFAULT_SETTINGS` 內新增（接在 `PRIVACY_STORE_EVENT_VECTOR_ONLY` 之後即可）：

```python
    # ── 會員制 ─────────────────────────────────────────────────────
    "MEMBER_ENABLED": True,            # 總開關；false 時 kiosk 跳過選擇頁、後台隱藏分頁
    "MEMBER_USUALS_COUNT": 8,          # 「您的常點」顯示品項數
    "MEMBER_PUSH_WEIGHT": 4,           # 會員常點品項於 ai_push 加權倍率
    "MEMBER_ORDERS_KEEP": 20,          # 每位會員保留近期訂單筆數
```

`PUBLIC_SETTINGS_KEYS` 集合內新增兩行：

```python
    "MEMBER_ENABLED",
    "MEMBER_USUALS_COUNT",
```

- [ ] **Step 2: 寫失敗測試**

`UI_API/tests/test_member_routes.py`（用 FastAPI TestClient + 最小 app，避開完整 lifespan）：

```python
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from repositories import member_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    from services import member_service
    importlib.reload(member_service)
    member_service._session_member.clear()
    from routes import member_routes
    importlib.reload(member_routes)
    app = FastAPI()
    app.include_router(member_routes.create_router({}))
    return TestClient(app)


def test_register_then_login(client):
    r = client.post("/api/member/register", data={"session_id": "s1", "phone": "0912345678", "nickname": "小明"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["member"]["nickname"] == "小明"

    r2 = client.post("/api/member/login", data={"session_id": "s2", "phone": "0912345678"})
    assert r2.json()["found"] is True


def test_login_not_found(client):
    r = client.post("/api/member/login", data={"session_id": "s1", "phone": "0900000000"})
    assert r.json() == {"found": False}


def test_admin_list_and_detail(client):
    client.post("/api/member/register", data={"session_id": "s1", "phone": "0912345678", "nickname": "小明"})
    rows = client.get("/api/members").json()
    assert isinstance(rows, list) and rows[0]["phone_masked"] == "0912-***-678"
    detail = client.get("/api/members/0912345678").json()
    assert detail["nickname"] == "小明"
    assert client.get("/api/members/0900000000").status_code == 404
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_routes.py -v`
Expected: FAIL（`No module named 'routes.member_routes'`）

- [ ] **Step 4: 實作 member_routes**

`UI_API/backend/routes/member_routes.py`：

```python
import asyncio

from fastapi import APIRouter, Form, HTTPException, Request

from services import member_service
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter()

    @router.post("/api/member/login")
    async def member_login(session_id: str = Form(...), phone: str = Form(...)):
        return await asyncio.to_thread(member_service.login, session_id, phone)

    @router.post("/api/member/register")
    async def member_register(
        session_id: str = Form(...),
        phone: str = Form(...),
        nickname: str = Form(default=""),
    ):
        return await asyncio.to_thread(member_service.register, session_id, phone, nickname)

    @router.get("/api/members")
    async def list_members(request: Request):
        require_admin_token(request)
        return await asyncio.to_thread(member_service.admin_list)

    @router.get("/api/members/{phone}")
    async def member_detail(request: Request, phone: str):
        require_admin_token(request)
        detail = await asyncio.to_thread(member_service.admin_detail, phone)
        if detail is None:
            raise HTTPException(status_code=404, detail="member not found")
        return detail

    return router
```

- [ ] **Step 5: 掛載到 main.py**

`main.py` 的 routes import tuple（`:15-27`）加入 `member_routes,`；在 include_router 區塊（接在 `passive_voice_routes` 後）新增：

```python
app.include_router(member_routes.create_router(_deps))
```

- [ ] **Step 6: 跑測試 + 編譯確認通過**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_member_routes.py -v && python3 -m py_compile main.py config.py backend/routes/member_routes.py`
Expected: PASS（4 passed）+ 編譯無輸出

- [ ] **Step 7: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/config.py UI_API/backend/routes/member_routes.py UI_API/main.py UI_API/tests/test_member_routes.py
git commit -m "feat(member): MEMBER_* settings + member routes (login/register/admin)"
```

---

### Task 6: ai_push 會員個人化（常點加權 + LLM context）

**Files:**
- Modify: `UI_API/backend/services/ai_push_service.py:43-52`（`_weighted_pick`）、`:65-106`（`generate`）
- Test: `UI_API/tests/test_ai_push_member.py`

**Interfaces:**
- Consumes: `member_service.get_session_member/member_top_ids/member_push_context`
- Produces: `_weighted_pick(items, exclude, top_weight=3, member_ids=None)`（新增 `member_ids` 參數，會員品項權重 `config.get("MEMBER_PUSH_WEIGHT", 4)`）

- [ ] **Step 1: 寫失敗測試**

`UI_API/tests/test_ai_push_member.py`：

```python
import importlib


def test_weighted_pick_boosts_member_items(monkeypatch):
    from services import ai_push_service
    importlib.reload(ai_push_service)
    monkeypatch.setattr(ai_push_service, "get_top_items", lambda n=3: [])
    monkeypatch.setattr(ai_push_service.config, "get", lambda k, d=None: 50 if k == "MEMBER_PUSH_WEIGHT" else d)
    items = [{"id": "MCD001", "price": 100}, {"id": "MCD012", "price": 50}]
    # 會員常點 MCD012，權重 50 倍 → 100 次抽樣應壓倒性命中 MCD012
    hits = [ai_push_service._weighted_pick(items, set(), 3, ["MCD012"])["id"] for _ in range(100)]
    assert hits.count("MCD012") > 90


def test_weighted_pick_no_member_unchanged(monkeypatch):
    from services import ai_push_service
    importlib.reload(ai_push_service)
    monkeypatch.setattr(ai_push_service, "get_top_items", lambda n=3: [])
    items = [{"id": "MCD001", "price": 100}]
    assert ai_push_service._weighted_pick(items, set(), 3, None)["id"] == "MCD001"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_ai_push_member.py -v`
Expected: FAIL（`_weighted_pick()` 不接受第 4 個位置參數）

- [ ] **Step 3: 修改 _weighted_pick**

`ai_push_service.py` 的 `_weighted_pick` 整段取代：

```python
def _weighted_pick(items: list[dict], exclude: set, top_weight: int = 3, member_ids=None) -> dict | None:
    """加權隨機選品：TOP3 權重 top_weight 倍、會員常點權重 MEMBER_PUSH_WEIGHT 倍，其餘等機率。"""
    candidates = [i for i in items if i.get("id") and i["id"] not in exclude and _price(i) > 0]
    if not candidates:
        return None
    top_ids = {t["id"] for t in get_top_items(3)}
    member_set = set(member_ids or [])
    member_weight = int(config.get("MEMBER_PUSH_WEIGHT", 4))
    pool = []
    for item in candidates:
        weight = 1
        if item["id"] in top_ids:
            weight = max(weight, top_weight)
        if item["id"] in member_set:
            weight = max(weight, member_weight)
        pool.extend([item] * weight)
    return random.choice(pool)
```

- [ ] **Step 4: generate() 反查會員並注入**

在 `ai_push_service.py` 頂部 import 區新增：

```python
from services import member_service
```

`generate()` 內，將選品段（`picked = await asyncio.to_thread(_weighted_pick, items, exclude)`）改為：

```python
    member = member_service.get_session_member(session_id)
    member_ids = member_service.member_top_ids(member) if member else []
    picked = await asyncio.to_thread(_weighted_pick, items, exclude, 3, member_ids)
```

並在組 `user` prompt 處，於 `rag_section` 之後插入會員 context。把現有：

```python
    user = (
        f"{rag_section}"
        f"【指定推播餐點】{sel_id}｜{sel_name}\n\n"
```

改為：

```python
    member_section = ""
    if member:
        ctx = member_service.member_push_context(member)
        if ctx:
            member_section = f"{ctx}\n\n"
    user = (
        f"{rag_section}"
        f"{member_section}"
        f"【指定推播餐點】{sel_id}｜{sel_name}\n\n"
```

- [ ] **Step 5: 跑測試 + 編譯確認通過**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_ai_push_member.py -v && python3 -m py_compile backend/services/ai_push_service.py`
Expected: PASS（2 passed）+ 編譯無輸出

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/backend/services/ai_push_service.py UI_API/tests/test_ai_push_member.py
git commit -m "feat(member): personalize ai_push via member usuals weighting + LLM context"
```

---

### Task 7: 結帳整合（cart_total + finalize_checkout）

**Files:**
- Modify: `UI_API/backend/routes/core_routes.py:95-120`（checkout route 加 `cart_total`）
- Modify: `UI_API/backend/services/checkout_service.py:68-117`（`process_checkout` 加 `cart_total` + 呼叫 finalize）
- Modify: `UI_API/frontend/pos/app.js:1370-1376`（`writeCheckoutLog` 加 `cart_total`）
- Test: `UI_API/tests/test_checkout_member.py`

**Interfaces:**
- Consumes: `member_service.finalize_checkout`
- Produces: `checkout_service.process_checkout(session_id, pushed_list, cart_list, ai_count, sources, cart_total=0)`

- [ ] **Step 1: 寫失敗測試**

`UI_API/tests/test_checkout_member.py`（驗證 finalize 被呼叫，且其例外不影響結帳回應）：

```python
import asyncio
import importlib


def test_process_checkout_calls_finalize(monkeypatch):
    from services import checkout_service
    importlib.reload(checkout_service)
    monkeypatch.setattr(checkout_service.database, "record_final_checkout",
                        lambda *a, **k: {"is_success": True})
    monkeypatch.setattr(checkout_service, "mark_latest_intervention_checkout", lambda *a, **k: None)
    monkeypatch.setattr(checkout_service.session_repository, "get_session_history", lambda sid: [])
    monkeypatch.setattr(checkout_service.session_repository, "archive_session", lambda sid: None)
    monkeypatch.setattr(checkout_service.log_repository, "get_session_logs", lambda: [])

    seen = {}
    def fake_finalize(session_id, cart_ids, total, ok):
        seen["args"] = (session_id, cart_ids, total, ok)
    monkeypatch.setattr(checkout_service.member_service, "finalize_checkout", fake_finalize)

    out = asyncio.run(checkout_service.process_checkout("s1", [], ["MCD001"], 0, [], 200))
    assert out["status"] == "success"
    assert seen["args"] == ("s1", ["MCD001"], 200, True)


def test_finalize_exception_does_not_break_checkout(monkeypatch):
    from services import checkout_service
    importlib.reload(checkout_service)
    monkeypatch.setattr(checkout_service.database, "record_final_checkout",
                        lambda *a, **k: {"is_success": False})
    monkeypatch.setattr(checkout_service, "mark_latest_intervention_checkout", lambda *a, **k: None)
    monkeypatch.setattr(checkout_service.session_repository, "get_session_history", lambda sid: [])
    monkeypatch.setattr(checkout_service.session_repository, "archive_session", lambda sid: None)
    monkeypatch.setattr(checkout_service.log_repository, "get_session_logs", lambda: [])

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(checkout_service.member_service, "finalize_checkout", boom)

    out = asyncio.run(checkout_service.process_checkout("s1", [], ["MCD001"], 0, [], 200))
    assert out["status"] == "success"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_checkout_member.py -v`
Expected: FAIL（`process_checkout` 不接受 `cart_total`、`checkout_service.member_service` 不存在）

- [ ] **Step 3: checkout_service 加 cart_total + finalize**

`checkout_service.py` 頂部 import 加：

```python
from services import member_service
```

`process_checkout` 簽章改為：

```python
async def process_checkout(
    session_id: str,
    pushed_list: list,
    cart_list: list,
    ai_count: int,
    sources: list,
    cart_total: int = 0,
) -> dict:
```

在 `order_number = len(...)` 之前、`mark_latest_intervention_checkout` 區塊之後，插入（finalize 為附帶副作用，包 try/except）：

```python
    try:
        await asyncio.to_thread(
            member_service.finalize_checkout, session_id, cart_list, cart_total, True
        )
    except Exception:
        pass
```

- [ ] **Step 4: checkout route 加 cart_total Form**

`core_routes.py` 的 `process_checkout` route：簽章加 `cart_total: str = Form(default="0")`，並在呼叫前解析、傳入：

```python
        try:
            total_val = int(float(cart_total or 0))
        except (TypeError, ValueError):
            total_val = 0

        return await checkout_service.process_checkout(
            session_id, pushed_list, cart_list, ai_count, sources, total_val
        )
```

- [ ] **Step 5: 前端結帳送 cart_total**

`app.js` 的 `writeCheckoutLog`（`:1370` 起），在 `fd.append('cart_sources', ...)` 後新增一行：

```javascript
  fd.append('cart_total', String(cartManager.getCartTotal()));
```

- [ ] **Step 6: 跑測試 + 編譯/語法確認通過**

Run: `cd /home/oliver/Project_2026/UI_API && conda run -n emotion_ui python -m pytest tests/test_checkout_member.py -v && python3 -m py_compile backend/services/checkout_service.py backend/routes/core_routes.py && node --check frontend/pos/app.js`
Expected: PASS（2 passed）+ 編譯/語法無輸出

- [ ] **Step 7: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/backend/services/checkout_service.py UI_API/backend/routes/core_routes.py UI_API/frontend/pos/app.js UI_API/tests/test_checkout_member.py
git commit -m "feat(member): thread cart_total + finalize member profile on checkout"
```

---

### Task 8: 前端會員流程（member.js + overlay + startBtn 改流程）

**Files:**
- Create: `UI_API/frontend/pos/member.js`
- Modify: `UI_API/frontend/pos/index.html`（新增三個 overlay：選擇頁/手機登入/快速註冊）
- Modify: `UI_API/frontend/pos/state.js`（加 `member: null`）
- Modify: `UI_API/frontend/pos/app.js:1234-1263`（`ui.startBtn.onclick` 流程）
- Modify: `UI_API/frontend/shared/api.js`（加 `memberLogin` / `memberRegister`）

**Interfaces:**
- Consumes（from app.js）：`sessionId`、`getRuntimeSettings`、既有 init 函式
- Produces（member.js export）：`showMemberChoice(onResolved)`、`getMember()`、`isMemberFlowVisible()`
  - `onResolved(member_or_null)`：使用者完成選擇（會員物件或 null=訪客）後呼叫，app.js 用它接續既有 init
- 無 JS 測試框架 → 以 `node --check` + 人工瀏覽器驗證。

- [ ] **Step 1: api.js 加會員 API**

`frontend/shared/api.js` 新增（仿照既有 `aiPush` FormData 風格）：

```javascript
export async function memberLogin(sessionId, phone) {
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('phone', phone);
  return asJson(await fetch(`${API_BASE}/api/member/login`, { method: 'POST', body: fd }));
}

export async function memberRegister(sessionId, phone, nickname) {
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('phone', phone);
  fd.append('nickname', nickname || '');
  return asJson(await fetch(`${API_BASE}/api/member/register`, { method: 'POST', body: fd }));
}
```

- [ ] **Step 2: state.js 加 member 欄位**

`frontend/pos/state.js` 的 `state` 物件加一欄：

```javascript
  member: null,
```

- [ ] **Step 3: index.html 加三個 overlay**

在 `startupOverlay`（`</div>` 結束後、`orderConfirmModal` 之前）插入：

```html
  <!-- 會員：選擇頁 -->
  <div id="memberChoiceOverlay" class="member-overlay hidden" aria-hidden="true">
    <div class="member-card">
      <div class="member-arches">M</div>
      <h2 class="member-welcome">歡迎光臨</h2>
      <p class="member-sub">請選擇您的點餐方式</p>
      <button id="memberChoiceMember" class="member-choice member" type="button">
        <span class="member-choice-badge">會員專屬</span>
        <strong>會員點餐</strong>
        <small>手機登入 · 專屬推薦 · 您的常點</small>
      </button>
      <button id="memberChoiceGuest" class="member-choice guest" type="button">
        <strong>直接點餐</strong>
        <small>免登入，立即開始</small>
      </button>
    </div>
  </div>

  <!-- 會員：手機登入 -->
  <div id="memberLoginOverlay" class="member-overlay hidden" aria-hidden="true">
    <div class="member-card">
      <button id="memberLoginBack" class="member-back" type="button">←</button>
      <h2 class="member-title">會員登入</h2>
      <p class="member-sub">請輸入手機號碼</p>
      <div id="memberPhoneDisplay" class="member-phone-display"></div>
      <p id="memberLoginHint" class="member-hint">輸入完整 10 碼後按「下一步」</p>
      <div id="memberKeypad" class="member-keypad">
        <button type="button" data-k="1">1</button><button type="button" data-k="2">2</button><button type="button" data-k="3">3</button>
        <button type="button" data-k="4">4</button><button type="button" data-k="5">5</button><button type="button" data-k="6">6</button>
        <button type="button" data-k="7">7</button><button type="button" data-k="8">8</button><button type="button" data-k="9">9</button>
        <button type="button" data-k="clear" class="fn">清除</button><button type="button" data-k="0">0</button><button type="button" data-k="back" class="fn">⌫</button>
      </div>
      <button id="memberLoginNext" class="member-primary" type="button">下一步 →</button>
      <button id="memberLoginSkip" class="member-skip" type="button">略過，直接點餐</button>
    </div>
  </div>

  <!-- 會員：快速註冊 -->
  <div id="memberRegisterOverlay" class="member-overlay hidden" aria-hidden="true">
    <div class="member-card">
      <button id="memberRegisterBack" class="member-back" type="button">←</button>
      <h2 class="member-title">快速註冊會員</h2>
      <p class="member-hint">這支號碼 <b id="memberRegisterPhone"></b> 還不是會員，輸入暱稱即可完成（可留空）</p>
      <input id="memberNicknameInput" class="member-input" type="text" maxlength="20" placeholder="暱稱（例如：小明）" />
      <button id="memberRegisterDone" class="member-primary" type="button">完成註冊並開始點餐 →</button>
      <button id="memberRegisterSkip" class="member-skip" type="button">略過，直接點餐</button>
    </div>
  </div>
```

並在 `frontend/shared/styles.css` 末端加入對應樣式（沿用既有 overlay/按鈕色系 `#da291c` / `#ffbc0d` / `#e8ddd4`）：

```css
.member-overlay { position:absolute; inset:0; z-index:60; display:flex; align-items:center; justify-content:center;
  background:rgba(40,32,24,.55); }
.member-overlay.hidden { display:none; }
.member-card { width:min(92vw,420px); background:#e8ddd4; border-radius:24px; padding:30px 26px; position:relative;
  display:flex; flex-direction:column; }
.member-arches { text-align:center; font-size:52px; font-weight:900; color:#ffbc0d; letter-spacing:-4px; }
.member-welcome,.member-title { text-align:center; color:#3a2c1f; font-size:24px; font-weight:800; margin:10px 0 4px; }
.member-sub { text-align:center; color:#8a7866; font-size:15px; margin-bottom:22px; }
.member-choice { border:none; border-radius:18px; padding:22px; margin-bottom:16px; text-align:left; cursor:pointer;
  display:flex; flex-direction:column; gap:4px; }
.member-choice.member { background:linear-gradient(135deg,#da291c,#b3160c); color:#fff; }
.member-choice.guest { background:#fff; color:#2a2018; border:2px solid #e0d3c6; }
.member-choice strong { font-size:20px; } .member-choice small { font-size:13px; opacity:.9; }
.member-choice-badge { align-self:flex-start; background:#ffbc0d; color:#3a2c1f; font-size:11px; font-weight:800;
  padding:2px 9px; border-radius:20px; }
.member-back { position:absolute; top:20px; left:18px; width:40px; height:40px; border-radius:12px; border:1px solid #e0d3c6;
  background:#fff; color:#6b5d4f; font-size:18px; cursor:pointer; }
.member-phone-display { background:#fff; border:2px solid #e0d3c6; border-radius:14px; height:64px; display:flex;
  align-items:center; justify-content:center; font-size:30px; font-weight:800; letter-spacing:3px; color:#2a2018; }
.member-hint { text-align:center; font-size:12.5px; color:#a8978a; margin:8px 0 18px; min-height:16px; }
.member-keypad { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.member-keypad button { background:#fff; border:1px solid #e6dace; border-radius:14px; min-height:58px; font-size:26px;
  font-weight:700; color:#2a2018; cursor:pointer; }
.member-keypad button.fn { background:#efe6dc; font-size:18px; color:#6b5d4f; }
.member-input { background:#fff; border:2px solid #e0d3c6; border-radius:14px; height:56px; padding:0 16px; font-size:18px;
  color:#2a2018; margin-bottom:18px; }
.member-primary { background:linear-gradient(135deg,#da291c,#b3160c); color:#fff; border:none; border-radius:16px;
  height:58px; font-size:18px; font-weight:800; cursor:pointer; margin-top:18px; }
.member-skip { background:none; border:none; color:#8a7866; font-size:13px; text-decoration:underline; cursor:pointer;
  margin-top:14px; }
```

- [ ] **Step 4: 實作 member.js**

`frontend/pos/member.js`：

```javascript
// =========================================================
// 會員流程：選擇頁 → 手機登入 → (查無→快速註冊) → 完成回呼。
// onResolved(member|null)：member 物件代表已登入會員，null 代表訪客。
// =========================================================
import * as api from '../shared/api.js';
import { state } from './state.js';
import { sessionId } from './app.js';

const $ = (id) => document.getElementById(id);
let _phone = '';
let _onResolved = null;

function show(el) { el?.classList.remove('hidden'); el?.setAttribute('aria-hidden', 'false'); }
function hide(el) { el?.classList.add('hidden'); el?.setAttribute('aria-hidden', 'true'); }

function hideAll() {
  ['memberChoiceOverlay', 'memberLoginOverlay', 'memberRegisterOverlay'].forEach((id) => hide($(id)));
}

export function getMember() { return state.member; }

export function isMemberFlowVisible() {
  return ['memberChoiceOverlay', 'memberLoginOverlay', 'memberRegisterOverlay']
    .some((id) => !$(id)?.classList.contains('hidden'));
}

function resolve(member) {
  hideAll();
  state.member = member || null;
  const cb = _onResolved;
  _onResolved = null;
  cb?.(state.member);
}

function renderPhone() {
  const el = $('memberPhoneDisplay');
  if (el) el.textContent = _phone || '';
  const next = $('memberLoginNext');
  if (next) next.disabled = _phone.length !== 10;
}

function onKey(k) {
  if (k === 'clear') _phone = '';
  else if (k === 'back') _phone = _phone.slice(0, -1);
  else if (/^\d$/.test(k) && _phone.length < 10) _phone += k;
  renderPhone();
}

async function submitLogin() {
  if (_phone.length !== 10) return;
  const res = await api.memberLogin(sessionId, _phone).catch(() => ({ found: false }));
  if (res && res.found && res.member) {
    resolve(res.member);
  } else {
    $('memberRegisterPhone').textContent = _phone;
    $('memberNicknameInput').value = '';
    hideAll();
    show($('memberRegisterOverlay'));
  }
}

async function submitRegister() {
  const nickname = String($('memberNicknameInput')?.value || '').trim();
  const res = await api.memberRegister(sessionId, _phone, nickname).catch(() => null);
  resolve(res && res.ok ? res.member : null);
}

export function showMemberChoice(onResolved) {
  _onResolved = onResolved;
  _phone = '';
  renderPhone();
  hideAll();
  show($('memberChoiceOverlay'));
}

// 事件綁定（模組載入時註冊一次；元素不存在則略過）
$('memberChoiceMember')?.addEventListener('click', () => { hideAll(); show($('memberLoginOverlay')); renderPhone(); });
$('memberChoiceGuest')?.addEventListener('click', () => resolve(null));
$('memberLoginBack')?.addEventListener('click', () => { hideAll(); show($('memberChoiceOverlay')); });
$('memberLoginSkip')?.addEventListener('click', () => resolve(null));
$('memberLoginNext')?.addEventListener('click', submitLogin);
$('memberRegisterBack')?.addEventListener('click', () => { hideAll(); show($('memberLoginOverlay')); });
$('memberRegisterSkip')?.addEventListener('click', () => resolve(null));
$('memberRegisterDone')?.addEventListener('click', submitRegister);
$('memberKeypad')?.addEventListener('click', (e) => {
  const k = e.target?.getAttribute?.('data-k');
  if (k) onKey(k);
});
```

- [ ] **Step 5: app.js startBtn 流程改為先出選擇頁**

`app.js` 頂部 import 區（與其他 `./xxx.js` import 並列）加：

```javascript
import { showMemberChoice } from './member.js';
```

把 `ui.startBtn.onclick` 內、`await loadRuntimeSettings();` 之後的「重型 init」抽成一個內部函式並依設定決定是否先走會員選擇。將 `ui.startBtn.onclick` 改為：

```javascript
ui.startBtn.onclick = async () => {
  if (isAdminMode()) return;
  await loadRuntimeSettings();
  if (getRuntimeSettings().MEMBER_ENABLED) {
    ui.overlay.classList.add('hidden');  // 收起開始頁，露出會員選擇 overlay
    showMemberChoice(() => { runPosStartup(); });
  } else {
    runPosStartup();
  }
};

async function runPosStartup() {
  try {
    const f = getFeatures();
    const needAudio = Boolean(f.voiceAssist);
    const needVideo = Boolean(getRuntimeSettings().EMOTION_LLAMA_ENABLED);
    const mediaReady = await ensureMediaTracks({ video: needVideo, audio: needAudio });
    if (!mediaReady && needAudio) console.warn('Media permission unavailable; POS flow continues without rolling buffer.');
    await loadMenu();
    applyFeaturesToPOS();
    ui.overlay.style.opacity = '0';
    setTimeout(() => { ui.overlay.classList.add('hidden'); }, 500);
    isSystemRunning = true;
    state.lastCartAddAt = Date.now();
    startPageDwellWatcher();
    setInteractionPage('menu_page', { source: 'start_system' });
    setTimeout(() => aiPush.start(), 600);
    if (f.voiceAssist) setupAskRecorder();
    if (getRuntimeSettings().EMOTION_LLAMA_ENABLED && state.stream) {
      const bufferSec = Math.max(
        Number(getRuntimeSettings().EMOTION_LLAMA_CLIP_SEC) || 2.0,
        Number(getRuntimeSettings().PAYMENT_EMOTION_CLIP_SEC) || 5.0,
      );
      startRollingBuffer(state.stream, bufferSec);
    }
  } catch { alert("無法存取攝影機與麥克風。"); }
  startPassiveListener();
}
```

（註：原 onclick 內用區域變數 `runtimeSettings` 直接讀；抽成 `runPosStartup` 後改用 `getRuntimeSettings()` 確保拿到最新值。其餘邏輯與原本逐行等價。）

- [ ] **Step 6: 語法檢查**

Run: `cd /home/oliver/Project_2026/UI_API && node --check frontend/pos/member.js && node --check frontend/pos/app.js && node --check frontend/pos/state.js && node --check frontend/shared/api.js`
Expected: 無輸出（語法 OK）

- [ ] **Step 7: 人工瀏覽器驗證**

啟動：`cd /home/oliver/Project_2026/UI_API && APP_PORT=8200 ADMIN_PORT=8201 ENABLE_NGROK=false conda run -n emotion_ui python main.py`，開 `http://127.0.0.1:8200`：
- 按「開始點餐」→ 出現會員/訪客選擇頁。
- 點「直接點餐」→ 進菜單（等同現狀）。
- 重整 → 按開始 →「會員點餐」→ 輸入 10 碼 → 「下一步」→ 查無 → 跳註冊頁 → 填暱稱 → 完成 → 進菜單。
- 重整 → 同號碼登入 → 直接進菜單（不再跳註冊）。
- 「略過，直接點餐」可從登入/註冊頁回到訪客流程。

- [ ] **Step 8: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/frontend/pos/member.js UI_API/frontend/pos/index.html UI_API/frontend/pos/state.js UI_API/frontend/pos/app.js UI_API/frontend/shared/api.js UI_API/frontend/shared/styles.css
git commit -m "feat(member): kiosk member/guest choice + phone login/register flow"
```

---

### Task 9: 前端菜單會員列 +「您的常點」橫向列

**Files:**
- Modify: `UI_API/frontend/pos/index.html`（菜單區頂部容器）
- Modify: `UI_API/frontend/pos/member.js`（render 會員列與 usuals）
- Modify: `UI_API/frontend/pos/app.js`（`runPosStartup` 成功後呼叫 render；usuals 一鍵加入沿用 cartManager）
- Modify: `UI_API/frontend/shared/styles.css`

**Interfaces:**
- Consumes: `state.member`（`{phone,nickname,visit_count,usuals:[{id,name,price,image,count}]}`）、app.js `cartManager`
- Produces（member.js export）：`renderMemberMenuHeader()`（無會員則隱藏容器）

- [ ] **Step 1: index.html 加容器**

在菜單內容最上方（POS 菜單 grid 之前）加入：

```html
<div id="memberMenuBar" class="member-menu-bar hidden">
  <div class="member-menu-id">
    <span id="memberMenuAvatar" class="member-menu-avatar"></span>
    <div>
      <div id="memberMenuName" class="member-menu-name"></div>
      <div id="memberMenuMeta" class="member-menu-meta"></div>
    </div>
  </div>
  <div class="member-usuals">
    <div class="member-usuals-title">🔁 您的常點</div>
    <div id="memberUsualsRow" class="member-usuals-row"></div>
  </div>
</div>
```

- [ ] **Step 2: styles.css 樣式**

```css
.member-menu-bar { background:linear-gradient(135deg,#fff7e8,#ffeccc); border-bottom:1px solid #f0dca5; padding:12px 16px; }
.member-menu-bar.hidden { display:none; }
.member-menu-id { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.member-menu-avatar { width:36px; height:36px; border-radius:50%; background:linear-gradient(135deg,#da291c,#b3160c);
  color:#fff; display:grid; place-items:center; font-weight:800; }
.member-menu-name { font-size:15px; font-weight:800; color:#2a2018; }
.member-menu-meta { font-size:11.5px; color:#9a8978; }
.member-usuals-title { font-size:14px; font-weight:800; color:#3a2c1f; margin-bottom:8px; }
.member-usuals-row { display:flex; gap:10px; overflow-x:auto; padding-bottom:3px; }
.member-usual-card { flex:0 0 110px; background:#fff; border:1px solid #f0dca5; border-radius:12px; padding:9px;
  position:relative; cursor:pointer; }
.member-usual-img { height:56px; border-radius:8px; background:#f3ece4; display:grid; place-items:center; font-size:26px;
  margin-bottom:6px; overflow:hidden; }
.member-usual-img img { width:100%; height:100%; object-fit:cover; }
.member-usual-name { font-size:12px; font-weight:700; color:#2a2018; line-height:1.3; height:31px; overflow:hidden; }
.member-usual-price { font-size:12.5px; font-weight:800; color:#da291c; }
.member-usual-count { position:absolute; top:6px; right:6px; background:#da291c; color:#fff; font-size:10px; font-weight:800;
  padding:1px 6px; border-radius:20px; }
```

- [ ] **Step 3: member.js 加 renderMemberMenuHeader（XSS 安全：textContent / DOM）**

於 member.js 加入並 export，import 既有視覺工具：

```javascript
import { getMenuVisual, formatItemPrice } from './menu_visuals.js';
import { cartManager } from './app.js';

export function renderMemberMenuHeader() {
  const bar = $('memberMenuBar');
  const m = state.member;
  if (!bar) return;
  if (!m) { bar.classList.add('hidden'); return; }
  bar.classList.remove('hidden');
  $('memberMenuAvatar').textContent = (m.nickname || '會員').slice(0, 1);
  $('memberMenuName').textContent = `歡迎回來，${m.nickname || '會員'} 👋`;
  $('memberMenuMeta').textContent = `第 ${m.visit_count + 1} 次光臨 · 會員`;

  const row = $('memberUsualsRow');
  row.textContent = '';
  const usuals = Array.isArray(m.usuals) ? m.usuals : [];
  if (!usuals.length) {
    const empty = document.createElement('div');
    empty.className = 'member-usuals-empty';
    empty.textContent = '首次點餐後，這裡會出現您的常點 ✨';
    empty.style.cssText = 'font-size:12px;color:#9a8978;padding:6px 2px';
    row.appendChild(empty);
    return;
  }
  usuals.forEach((item) => {
    const visual = getMenuVisual(item);
    const card = document.createElement('div');
    card.className = 'member-usual-card';

    const count = document.createElement('span');
    count.className = 'member-usual-count';
    count.textContent = `×${item.count}`;

    const img = document.createElement('div');
    img.className = 'member-usual-img';
    if (visual.image) {
      const el = document.createElement('img');
      el.src = visual.image; el.alt = item.name || '';
      el.onerror = () => { img.textContent = visual.emoji || '🍔'; };
      img.appendChild(el);
    } else {
      img.textContent = visual.emoji || '🍔';
    }

    const name = document.createElement('div');
    name.className = 'member-usual-name';
    name.textContent = item.name || '';

    const price = document.createElement('div');
    price.className = 'member-usual-price';
    price.textContent = formatItemPrice(item);

    card.append(count, img, name, price);
    card.addEventListener('click', () => {
      // cart.js 的 addToCart(item) 接收單一 item 物件（以 item.id 為 key），不是位置參數。
      cartManager.addToCart({ id: item.id, name: item.name, price: Number(item.price || 0) });
    });
    row.appendChild(card);
  });
}
```

- [ ] **Step 4: app.js 啟動成功後 render**

`runPosStartup()` 內 `setInteractionPage('menu_page', ...)` 之後加：

```javascript
    renderMemberMenuHeader();
```

並在頂部 member.js import 補上 `renderMemberMenuHeader`：

```javascript
import { showMemberChoice, renderMemberMenuHeader } from './member.js';
```

- [ ] **Step 5: 語法檢查**

Run: `cd /home/oliver/Project_2026/UI_API && node --check frontend/pos/member.js && node --check frontend/pos/app.js`
Expected: 無輸出

- [ ] **Step 6: 人工瀏覽器驗證**

重啟服務（指令同 Task 8 Step 7），`http://127.0.0.1:8200`：
- 新會員註冊後進菜單 → 會員列顯示「歡迎回來，{暱稱}」，常點列顯示「首次點餐後…」空狀態。
- 用該會員點 1～2 樣 → 結帳完成。重整 → 同號碼登入 → 菜單頂部出現「您的常點」卡片（含 ×次數），點卡片可加入購物車。
- 訪客流程：菜單頂部**不**顯示會員列。

- [ ] **Step 7: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/frontend/pos/index.html UI_API/frontend/pos/member.js UI_API/frontend/pos/app.js UI_API/frontend/shared/styles.css
git commit -m "feat(member): member menu header + your-usuals quick-reorder row"
```

---

### Task 10: 後台會員分頁（列表 + 詳情）

**Files:**
- Modify: `UI_API/frontend/admin/admin.html`（側欄 nav-item + members 頁面區塊）
- Modify: `UI_API/frontend/admin/admin.js`（fetch + render 列表/詳情）

**Interfaces:**
- Consumes: `GET /api/members`、`GET /api/members/{phone}`、公開設定 `MEMBER_ENABLED`
- 無 JS 測試框架 → `node --check` + 人工瀏覽器驗證。XSS：暱稱/品名一律 `escHtml` 或 textContent。

- [ ] **Step 1: admin.html 加 nav-item + 頁面**

側欄 `nav`（emotion 之後）加：

```html
    <button class="nav-item" data-page="members" type="button">
      <i class="fas fa-user"></i> 會員
    </button>
```

並新增頁面區塊（與其他 `page-xxx` 區塊同層）。**注意：admin 的分頁切換是由 `admin.js:50` 的既有 click handler 以 `style.display` 切換 `[id^="page-"]`，不是 `.hidden` class**，所以區塊初始用 `style="display:none"`：

```html
<section id="page-members" style="display:none">
  <h1 class="page-title">會員管理</h1>
  <div id="memberStatCards" class="member-stat-cards"></div>
  <input id="memberSearch" class="member-search" type="text" placeholder="搜尋手機號碼或暱稱…" />
  <div class="adm-table-wrap">
    <table>
      <thead><tr><th>手機號碼</th><th>暱稱</th><th>光臨</th><th>累計消費</th><th>最近光臨</th><th>常點品項</th><th></th></tr></thead>
      <tbody id="memberTableBody"></tbody>
    </table>
  </div>
  <div id="memberDetailPanel" class="member-detail-panel hidden"></div>
</section>
```

- [ ] **Step 2: admin.js 加載入/渲染邏輯**

依 admin.js 既有的 page 切換機制（`data-page` → 顯示對應 `#page-xxx`）掛上 members 載入。新增（沿用既有 `escHtml` 工具；若名稱不同則用該檔既有的 HTML escape）：

```javascript
async function loadMembers() {
  const rows = await fetch('/api/members').then(r => r.json()).catch(() => []);
  window._memberRows = Array.isArray(rows) ? rows : [];
  renderMemberStats(window._memberRows);
  renderMemberTable(window._memberRows);
}

function renderMemberStats(rows) {
  const total = rows.length;
  const weekAgo = Date.now() - 7 * 864e5;
  const active = rows.filter(r => Date.parse(r.last_visit_at || '') >= weekAgo).length;
  const visits = rows.reduce((s, r) => s + (r.visit_count || 0), 0);
  const spend = rows.reduce((s, r) => s + (r.total_spend || 0), 0);
  const avg = visits ? Math.round(spend / visits) : 0;
  const favFreq = {};
  rows.forEach(r => (r.favorites || []).forEach(f => { favFreq[f] = (favFreq[f] || 0) + 1; }));
  const topFav = Object.entries(favFreq).sort((a, b) => b[1] - a[1])[0]?.[0] || '—';
  const cards = [['總會員數', total], ['本週活躍', active], ['會員平均客單', '$' + avg], ['會員最愛品項', topFav]];
  document.getElementById('memberStatCards').innerHTML = cards
    .map(([label, val]) => `<div class="member-stat"><b>${escHtml(String(val))}</b><span>${escHtml(label)}</span></div>`)
    .join('');
}

function renderMemberTable(rows) {
  const body = document.getElementById('memberTableBody');
  body.innerHTML = '';
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    const favs = (r.favorites || []).map(f => `<span class="fav-chip">${escHtml(f)}</span>`).join('');
    tr.innerHTML = `<td>${escHtml(r.phone_masked || '')}</td><td>${escHtml(r.nickname || '')}</td>`
      + `<td>${r.visit_count || 0} 次</td><td>$${r.total_spend || 0}</td>`
      + `<td>${escHtml(r.last_visit_at ? r.last_visit_at.slice(0, 10) : '—')}</td><td>${favs}</td>`
      + `<td><button class="view-btn" data-phone="${escHtml(r.phone || '')}">查看</button></td>`;
    body.appendChild(tr);
  });
  body.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', () => loadMemberDetail(btn.getAttribute('data-phone')));
  });
}

async function loadMemberDetail(phone) {
  const d = await fetch(`/api/members/${encodeURIComponent(phone)}`).then(r => r.ok ? r.json() : null).catch(() => null);
  const panel = document.getElementById('memberDetailPanel');
  if (!d) { panel.classList.add('hidden'); return; }
  const favRows = (d.favorites_ranked || []).map(f =>
    `<div class="fav-row"><span>${escHtml(f.name)}</span><b>×${f.count}</b></div>`).join('');
  const orderRows = (d.orders || []).map(o => {
    const items = (o.cart_ids || []).map(escHtml).join('、');
    const hit = o.is_success ? '<span class="hit">⭐ 推播命中</span>' : '';
    return `<div class="order-row"><div><span>${escHtml((o.timestamp || '').slice(0, 16).replace('T', ' '))}</span>`
      + `<b>$${o.total || 0}</b></div><div class="order-items">${items}</div>${hit}</div>`;
  }).join('');
  panel.classList.remove('hidden');
  panel.innerHTML = `<h2>${escHtml(d.nickname || '')}　<small>${escHtml(d.phone_masked || '')}</small></h2>`
    + `<div class="member-kpis"><div><b>${d.visit_count}</b><span>光臨</span></div>`
    + `<div><b>$${d.total_spend}</b><span>累計消費</span></div>`
    + `<div><b>$${d.avg_spend}</b><span>平均客單</span></div></div>`
    + `<h3>🔁 常點品項排行</h3>${favRows || '<p class="muted">尚無紀錄</p>'}`
    + `<h3>🧾 歷次訂單</h3>${orderRows || '<p class="muted">尚無訂單</p>'}`;
}
```

把 `loadMembers()` 接到 page 切換：`admin.js:50` 既有的 nav click handler 內（取得 `const page = btn.dataset.page;` 之後）加入：

```javascript
    if (page === 'members') loadMembers();
```

並加入最小樣式（admin.html 既有 `<style>` 內或檔末）：

```css
.member-stat-cards { display:flex; gap:12px; margin-bottom:14px; }
.member-stat { flex:1; background:#fff; border:1px solid #e7ebf0; border-radius:11px; padding:12px 14px; }
.member-stat b { display:block; font-size:20px; color:#222; } .member-stat span { font-size:11.5px; color:#8a94a3; }
.member-search { width:100%; max-width:320px; background:#fff; border:1px solid #dde2e8; border-radius:9px;
  padding:9px 13px; margin-bottom:14px; }
.fav-chip { display:inline-block; background:#f3ece4; color:#6b5d4f; border-radius:6px; padding:2px 7px;
  font-size:11px; margin-right:4px; }
.view-btn { background:#3b7aee; color:#fff; border:none; border-radius:7px; padding:6px 12px; cursor:pointer; }
.member-detail-panel { background:#fff; border:1px solid #e7ebf0; border-radius:12px; padding:18px; margin-top:16px; }
.member-detail-panel.hidden { display:none; }
.member-kpis { display:flex; gap:14px; margin:10px 0 6px; }
.member-kpis div { background:#f7f9fb; border-radius:9px; padding:9px 14px; text-align:center; }
.member-kpis b { display:block; font-size:17px; } .member-kpis span { font-size:10.5px; color:#8a94a3; }
.fav-row { display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid #f0f2f5; }
.order-row { border:1px solid #eef1f5; border-radius:9px; padding:10px 12px; margin-bottom:9px; }
.order-row > div:first-child { display:flex; justify-content:space-between; }
.order-items { font-size:12px; color:#6b5d4f; margin-top:5px; } .hit { font-size:11px; color:#2e9e5b; }
.muted { color:#9aa4b1; font-size:12.5px; }
```

- [ ] **Step 3: MEMBER_ENABLED 隱藏分頁**

admin.js 載入設定後（既有 `loadSettings` 流程），若 `settings.MEMBER_ENABLED === false`，隱藏 `data-page="members"` 的 nav-item：

```javascript
if (settings.MEMBER_ENABLED === false) {
  const tab = document.querySelector('.nav-item[data-page="members"]');
  if (tab) tab.style.display = 'none';
}
```

- [ ] **Step 4: 語法檢查**

Run: `cd /home/oliver/Project_2026/UI_API && node --check frontend/admin/admin.js`
Expected: 無輸出

- [ ] **Step 5: 人工瀏覽器驗證**

重啟服務，開後台 `http://127.0.0.1:8201`：
- 側欄出現「👤 會員」分頁，點擊 → 顯示統計卡 + 會員列表（手機遮罩）。
- 點某會員「查看」→ 下方顯示詳情（KPI、常點排行、歷次訂單、推播命中標記）。
- 暱稱含特殊字元（如先在 kiosk 註冊暱稱 `<b>x`）→ 後台顯示為純文字，不被當 HTML（XSS 驗證）。

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/Project_2026 && git add UI_API/frontend/admin/admin.html UI_API/frontend/admin/admin.js
git commit -m "feat(member): admin members tab — list + detail view"
```

---

## 完成後

全部 task 完成後，依 subagent-driven-development 流程：跑一次全分支 code review（`scripts/review-package MERGE_BASE HEAD`），再用 `superpowers:finishing-a-development-branch` 決定合併策略。

建議在實作前先開分支：`git checkout -b feature/membership`。
