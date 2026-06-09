# pos_agent Multi-Agent Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-stage agent core + minimal API of `pos_agent` at `/home/oliver/pos_agent` — a multi-agent, tool-calling self-ordering backend with switchable Claude/Gemini/Ollama providers, provable via a text `/api/chat` endpoint and a CLI.

**Architecture:** Three abstraction layers — (1) `LLMProvider` normalizes tool-calling across Claude/Gemini/Ollama into one `run(messages, tools) -> LLMResponse` interface; (2) a Tool Registry where each `ToolSpec` carries a JSON-schema + handler that mutates a shared `AgentContext` (whitelist enforced inside `add_to_cart`, not by the LLM); (3) an `Agent` base that runs the tool-calling loop. Four agents (Orchestrator router → Ordering / Recommendation / Intervention) sit on top. Everything is TDD-verified with a scripted `FakeProvider` so no real LLM is needed in tests.

**Tech Stack:** Python 3.x, FastAPI, pytest, `requests` (Ollama HTTP), `anthropic` SDK (Claude), `google-genai` SDK (Gemini). Bare intra-package imports (`from llm.provider import ...`) with `app/` as the source root, mirroring Project_2026's conventions.

---

## File Structure

```
pos_agent/
├── CLAUDE.md                  ← Task 16
├── README.md                  ← Task 16
├── requirements.txt           ← Task 1
├── pyproject.toml             ← Task 1 (pytest pythonpath=["app"])
├── .env.example               ← Task 1
├── .gitignore                 ← Task 1
├── conftest.py                ← Task 2 (shared menu fixture)
├── cli.py                     ← Task 15
├── data/
│   └── menu.json              ← Task 1 (copied from Project_2026)
├── app/
│   ├── config.py              ← Task 1
│   ├── context.py             ← Task 3
│   ├── main.py                ← Task 14
│   ├── domain/
│   │   └── menu.py            ← Task 2
│   ├── llm/
│   │   ├── provider.py        ← Task 4   (Message/ToolCall/LLMResponse/LLMProvider)
│   │   ├── fake_provider.py   ← Task 4
│   │   ├── ollama_provider.py ← Task 9
│   │   ├── claude_provider.py ← Task 10
│   │   ├── gemini_provider.py ← Task 11
│   │   └── factory.py         ← Task 12
│   ├── tools/
│   │   ├── registry.py        ← Task 5
│   │   ├── menu_tools.py      ← Task 6
│   │   ├── cart_tools.py      ← Task 6
│   │   ├── recommend_tools.py ← Task 7
│   │   ├── staff_tools.py     ← Task 7
│   │   ├── kb_tools.py        ← Task 7
│   │   └── builtin.py         ← Task 7 (import side-effect: registers all tools)
│   ├── agents/
│   │   ├── base.py            ← Task 8
│   │   ├── ordering_agent.py  ← Task 13
│   │   ├── recommendation_agent.py ← Task 13
│   │   ├── intervention_agent.py   ← Task 13
│   │   └── orchestrator.py    ← Task 13
│   ├── prompts/
│   │   └── defaults.py        ← Task 13
│   └── api/
│       ├── chat_routes.py     ← Task 14
│       ├── menu_routes.py     ← Task 14
│       └── event_routes.py    ← Task 14
└── tests/
    ├── test_menu.py           ← Task 2
    ├── test_context.py        ← Task 3
    ├── test_fake_provider.py  ← Task 4
    ├── test_registry.py       ← Task 5
    ├── test_cart_tools.py     ← Task 6
    ├── test_recommend_tools.py← Task 7
    ├── test_agent_loop.py     ← Task 8
    ├── test_ollama_provider.py← Task 9
    ├── test_claude_provider.py← Task 10
    ├── test_gemini_provider.py← Task 11
    ├── test_factory.py        ← Task 12
    ├── test_agents.py         ← Task 13
    └── test_api.py            ← Task 14
```

> **Import rule (all tasks):** `app/` is the source root. Use bare imports (`from llm.provider import Message`, `import config`). pytest finds them via `pythonpath = ["app"]`; `cli.py`/`main.py` work because their own dir logic puts `app/` on `sys.path`.

> **Each task ends in a commit.** All `git` commands assume cwd `/home/oliver/pos_agent`.

---

## Task 1: Project scaffold

**Files:**
- Create: `/home/oliver/pos_agent/requirements.txt`
- Create: `/home/oliver/pos_agent/pyproject.toml`
- Create: `/home/oliver/pos_agent/.gitignore`
- Create: `/home/oliver/pos_agent/.env.example`
- Create: `/home/oliver/pos_agent/app/config.py`
- Create: `/home/oliver/pos_agent/app/__init__.py` and all package `__init__.py` files
- Create: `/home/oliver/pos_agent/data/menu.json` (copied)

- [ ] **Step 1: Create directories, package markers, and copy the menu**

```bash
mkdir -p /home/oliver/pos_agent/app/{domain,llm,tools,agents,prompts,api}
mkdir -p /home/oliver/pos_agent/{data,tests}
cd /home/oliver/pos_agent
# package markers (app is source root; sub-packages need __init__.py)
touch app/__init__.py app/domain/__init__.py app/llm/__init__.py \
      app/tools/__init__.py app/agents/__init__.py app/prompts/__init__.py app/api/__init__.py
touch tests/__init__.py
cp /home/oliver/Project_2026/UI_API/menu_data/menu.json data/menu.json
git init -q
python3 -c "import json; d=json.load(open('data/menu.json')); print('menu items:', len(d), '| first id:', d[0]['id'])"
```
Expected: `menu items: 138 | first id: MCD001`

- [ ] **Step 2: Write `requirements.txt`**

```
fastapi>=0.110
uvicorn>=0.29
pydantic>=2.6
requests>=2.31
pytest>=7.4
httpx>=0.27
anthropic>=0.39
google-genai>=0.3
python-dotenv>=1.0
```

- [ ] **Step 3: Write `pyproject.toml`** (makes `app/` importable in tests)

```toml
[tool.pytest.ini_options]
pythonpath = ["app"]
testpaths = ["tests"]
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
.env
data/sessions/
data/settings.json
.pytest_cache/
.venv/
```

- [ ] **Step 5: Write `.env.example`**

```
# 雲端 provider 金鑰（用本地 ollama 時可留空）
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
# 預設使用的 LLM provider: ollama | claude | gemini
LLM_PROVIDER=ollama
```

- [ ] **Step 6: Write `app/config.py`**

```python
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

_APP_DIR = Path(__file__).resolve().parent          # app/
_PROJECT = _APP_DIR.parent                          # pos_agent/

DEFAULT_SETTINGS = {
    "LLM_PROVIDER": "ollama",                       # ollama | claude | gemini
    "LLM_FALLBACK_PROVIDER": "ollama",
    "OLLAMA_API_URL": "http://127.0.0.1:11434/api/chat",
    "OLLAMA_MODEL": "qwen3.5:4b",
    "OLLAMA_TIMEOUT": 120,
    "CLAUDE_MODEL": "claude-sonnet-4-6",
    "GEMINI_MODEL": "gemini-2.5-flash",
    "LLM_TEMPERATURE": 0.7,
    "LLM_MAX_TOKENS": 512,
    "AGENT_MAX_ITERS": 6,
    "MENU_JSON_PATH": str(_PROJECT / "data" / "menu.json"),
    "RAG_ENABLED": False,
    "VOICE_ENABLED": False,
}

_SETTINGS_PATH = _PROJECT / "data" / "settings.json"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")


def _load_dynamic() -> dict:
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get(key: str, default=None):
    """讀設定統一入口。優先序：環境變數 > settings.json > DEFAULT_SETTINGS > default。"""
    if key in os.environ:
        return os.environ[key]
    dyn = _load_dynamic()
    if key in dyn:
        return dyn[key]
    if key in DEFAULT_SETTINGS:
        return DEFAULT_SETTINGS[key]
    return default
```

- [ ] **Step 7: Verify config imports and resolves the menu path**

Run:
```bash
cd /home/oliver/pos_agent && PYTHONPATH=app python3 -c "import config; print(config.get('LLM_PROVIDER')); print(config.get('MENU_JSON_PATH'))"
```
Expected: prints `ollama` and an absolute path ending in `pos_agent/data/menu.json`.

- [ ] **Step 8: Commit**

```bash
cd /home/oliver/pos_agent
git add -A
git commit -m "chore: scaffold pos_agent project (config, deps, menu data)"
```

---

## Task 2: Menu domain + whitelist

**Files:**
- Create: `/home/oliver/pos_agent/conftest.py`
- Create: `/home/oliver/pos_agent/app/domain/menu.py`
- Test: `/home/oliver/pos_agent/tests/test_menu.py`

- [ ] **Step 1: Write the shared test fixture `conftest.py`**

```python
import json
import pytest

SAMPLE_MENU = [
    {"id": "MCD001", "category": "早餐", "name": "滿福堡",
     "description": "經典早餐堡", "aliases": ["mcmuffin", "早餐堡"], "price": 58},
    {"id": "MCD050", "category": "主餐", "name": "大麥克",
     "description": "經典牛肉堡", "aliases": ["big mac", "麥香"], "price": 75},
    {"id": "MCD120", "category": "飲料", "name": "可口可樂",
     "description": "冰涼汽水", "aliases": ["coke", "可樂"], "price": 35},
]


@pytest.fixture
def menu_file(tmp_path, monkeypatch):
    """Point MENU_JSON_PATH at a tiny fixture menu and reset the module cache."""
    p = tmp_path / "menu.json"
    p.write_text(json.dumps(SAMPLE_MENU, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("MENU_JSON_PATH", str(p))
    from domain import menu
    menu._cache["items"] = None
    menu._cache["mtime"] = None
    return p
```

- [ ] **Step 2: Write the failing test `tests/test_menu.py`**

```python
from domain import menu


def test_load_menu_reads_fixture(menu_file):
    items = menu.load_menu()
    assert len(items) == 3
    assert items[0]["id"] == "MCD001"


def test_get_item_found_and_missing(menu_file):
    assert menu.get_item("MCD050")["name"] == "大麥克"
    assert menu.get_item("MCD999") is None


def test_is_valid_item(menu_file):
    assert menu.is_valid_item("MCD001") is True
    assert menu.is_valid_item("NOPE") is False


def test_search_matches_name_and_alias(menu_file):
    assert [i["id"] for i in menu.search("可樂")] == ["MCD120"]
    assert [i["id"] for i in menu.search("big mac")] == ["MCD050"]


def test_compact_context_lists_ids(menu_file):
    ctx = menu.compact_context()
    assert "MCD001" in ctx and "大麥克" in ctx
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_menu.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.menu'` (or import error).

- [ ] **Step 4: Write `app/domain/menu.py`**

```python
import json
import os

import config

_cache = {"items": None, "mtime": None}


def _path() -> str:
    return config.get("MENU_JSON_PATH", "data/menu.json")


def load_menu() -> list:
    path = _path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    if _cache["items"] is not None and _cache["mtime"] == mtime:
        return _cache["items"]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data if isinstance(data, list) else []
    _cache["items"] = items
    _cache["mtime"] = mtime
    return items


def get_item(item_id: str) -> dict | None:
    for it in load_menu():
        if it.get("id") == item_id:
            return it
    return None


def is_valid_item(item_id: str) -> bool:
    return get_item(item_id) is not None


def search(query: str, limit: int = 8) -> list:
    q = (query or "").strip().lower()
    if not q:
        return load_menu()[:limit]
    hits = []
    for it in load_menu():
        hay = " ".join([
            str(it.get("name", "")),
            str(it.get("category", "")),
            str(it.get("description", "")),
            " ".join(it.get("aliases", []) or []),
        ]).lower()
        if q in hay:
            hits.append(it)
    return hits[:limit]


def compact_context(limit: int = 60) -> str:
    lines = [
        f"{it.get('id')} | {it.get('name')} | {it.get('category')} | ${it.get('price')}"
        for it in load_menu()[:limit]
    ]
    return "【菜單】\n" + "\n".join(lines)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_menu.py -q`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/pos_agent
git add app/domain/menu.py tests/test_menu.py conftest.py
git commit -m "feat: menu domain with whitelist lookup + search"
```

---

## Task 3: AgentContext

**Files:**
- Create: `/home/oliver/pos_agent/app/context.py`
- Test: `/home/oliver/pos_agent/tests/test_context.py`

- [ ] **Step 1: Write the failing test `tests/test_context.py`**

```python
from context import AgentContext


def test_add_and_drain_cart_actions():
    ctx = AgentContext(session_id="s1")
    ctx.add_cart_action({"action": "add", "item_id": "MCD001"})
    ctx.add_cart_action({"action": "add", "item_id": "MCD050"})
    drained = ctx.drain_cart_actions()
    assert len(drained) == 2
    assert ctx.drain_cart_actions() == []   # draining empties the buffer


def test_defaults():
    ctx = AgentContext()
    assert ctx.session_id == "anonymous"
    assert ctx.cart == [] and ctx.trace == [] and ctx.mood is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_context.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'context'`.

- [ ] **Step 3: Write `app/context.py`**

```python
from dataclasses import dataclass, field


@dataclass
class AgentContext:
    session_id: str = "anonymous"
    cart: list = field(default_factory=list)
    history: list = field(default_factory=list)
    mood: int | None = None
    cart_actions: list = field(default_factory=list)
    trace: list = field(default_factory=list)

    def add_cart_action(self, action: dict) -> None:
        self.cart_actions.append(action)

    def drain_cart_actions(self) -> list:
        out = self.cart_actions
        self.cart_actions = []
        return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_context.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/context.py tests/test_context.py
git commit -m "feat: AgentContext shared state with cart-action buffer"
```

---

## Task 4: LLM provider types + FakeProvider

**Files:**
- Create: `/home/oliver/pos_agent/app/llm/provider.py`
- Create: `/home/oliver/pos_agent/app/llm/fake_provider.py`
- Test: `/home/oliver/pos_agent/tests/test_fake_provider.py`

- [ ] **Step 1: Write the failing test `tests/test_fake_provider.py`**

```python
from llm.fake_provider import FakeProvider
from llm.provider import LLMResponse, Message, ToolCall


def test_fake_returns_scripted_in_order():
    fake = FakeProvider([
        LLMResponse(tool_calls=[ToolCall(id="1", name="search_menu", arguments={"query": "可樂"})]),
        LLMResponse(text="好的，已為您處理。"),
    ])
    r1 = fake.run([Message("user", "我要可樂")], [])
    assert r1.tool_calls[0].name == "search_menu"
    r2 = fake.run([], [])
    assert r2.text == "好的，已為您處理。"


def test_fake_records_calls_and_handles_exhaustion():
    fake = FakeProvider([])
    out = fake.run([Message("user", "hi")], ["toolspec"])
    assert "no more" in out.text.lower()
    assert len(fake.calls) == 1
    assert fake.calls[0][1] == ["toolspec"]   # tools recorded
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_fake_provider.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm.provider'`.

- [ ] **Step 3: Write `app/llm/provider.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, Sequence

if TYPE_CHECKING:                       # avoid runtime import cycle with tools.registry
    from tools.registry import ToolSpec


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Message:
    role: str                            # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    def run(self, messages: list[Message], tools: "Sequence[ToolSpec]") -> LLMResponse: ...
```

- [ ] **Step 4: Write `app/llm/fake_provider.py`**

```python
from llm.provider import LLMResponse


class FakeProvider:
    """Scripted provider for deterministic tests. Returns the given
    LLMResponse objects in order and records every (messages, tools) call.
    """
    name = "fake"

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = []

    def run(self, messages, tools):
        self.calls.append((list(messages), list(tools)))
        if self._scripted:
            return self._scripted.pop(0)
        return LLMResponse(text="(no more scripted responses)")
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_fake_provider.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/pos_agent
git add app/llm/provider.py app/llm/fake_provider.py tests/test_fake_provider.py
git commit -m "feat: LLM provider types (Message/ToolCall/LLMResponse) + FakeProvider"
```

---

## Task 5: Tool Registry

**Files:**
- Create: `/home/oliver/pos_agent/app/tools/registry.py`
- Test: `/home/oliver/pos_agent/tests/test_registry.py`

- [ ] **Step 1: Write the failing test `tests/test_registry.py`**

```python
from context import AgentContext
from tools.registry import ToolResult, ToolSpec, get_tool, get_tools, register


def _make_spec(name):
    return ToolSpec(
        name=name,
        description="desc",
        parameters={"type": "object", "properties": {}},
        handler=lambda args, ctx: ToolResult(content="ok"),
    )


def test_register_and_get():
    spec = register(_make_spec("dummy_tool"))
    assert get_tool("dummy_tool") is spec
    assert get_tool("missing") is None


def test_get_tools_filters_known_names():
    register(_make_spec("a_tool"))
    register(_make_spec("b_tool"))
    got = get_tools(["a_tool", "unknown", "b_tool"])
    assert [s.name for s in got] == ["a_tool", "b_tool"]


def test_handler_receives_args_and_ctx():
    captured = {}

    def handler(args, ctx):
        captured["args"] = args
        captured["sid"] = ctx.session_id
        return ToolResult(content="done")

    spec = register(ToolSpec("cap_tool", "d", {"type": "object"}, handler))
    res = spec.handler({"x": 1}, AgentContext(session_id="s9"))
    assert res.content == "done" and res.ok is True
    assert captured == {"args": {"x": 1}, "sid": "s9"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.registry'`.

- [ ] **Step 3: Write `app/tools/registry.py`**

```python
from dataclasses import dataclass
from typing import Callable

from context import AgentContext


@dataclass
class ToolResult:
    content: str
    ok: bool = True


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict                                       # JSON schema (object)
    handler: Callable[[dict, AgentContext], ToolResult]


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    _REGISTRY[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def get_tools(names: list[str]) -> list[ToolSpec]:
    return [_REGISTRY[n] for n in names if n in _REGISTRY]


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_registry.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/tools/registry.py tests/test_registry.py
git commit -m "feat: tool registry (ToolSpec/ToolResult/register/get_tools)"
```

---

## Task 6: Menu + cart tools (whitelist enforced)

**Files:**
- Create: `/home/oliver/pos_agent/app/tools/menu_tools.py`
- Create: `/home/oliver/pos_agent/app/tools/cart_tools.py`
- Test: `/home/oliver/pos_agent/tests/test_cart_tools.py`

- [ ] **Step 1: Write the failing test `tests/test_cart_tools.py`**

```python
import tools.cart_tools as cart_tools
import tools.menu_tools as menu_tools
from context import AgentContext


def test_search_menu_returns_matches(menu_file):
    res = menu_tools._search_menu({"query": "可樂"}, AgentContext())
    assert res.ok is True
    assert "MCD120" in res.content


def test_add_to_cart_valid_item_records_action(menu_file):
    ctx = AgentContext()
    res = cart_tools._add_to_cart({"item_id": "MCD050", "quantity": 2}, ctx)
    assert res.ok is True
    assert ctx.cart_actions == [
        {"action": "add", "item_id": "MCD050", "name": "大麥克", "quantity": 2}
    ]


def test_add_to_cart_rejects_non_whitelist_item(menu_file):
    ctx = AgentContext()
    res = cart_tools._add_to_cart({"item_id": "MCD999", "quantity": 1}, ctx)
    assert res.ok is False
    assert ctx.cart_actions == []          # nothing added on rejection


def test_remove_uses_name_when_known(menu_file):
    ctx = AgentContext()
    res = cart_tools._remove_from_cart({"item_id": "MCD001"}, ctx)
    assert res.ok is True
    assert ctx.cart_actions[0] == {"action": "remove", "item_id": "MCD001", "name": "滿福堡"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_cart_tools.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.cart_tools'`.

- [ ] **Step 3: Write `app/tools/menu_tools.py`**

```python
from context import AgentContext
from domain import menu
from tools.registry import ToolResult, ToolSpec, register


def _search_menu(args: dict, ctx: AgentContext) -> ToolResult:
    query = str(args.get("query", "")).strip()
    hits = menu.search(query, limit=int(args.get("limit", 8) or 8))
    if not hits:
        return ToolResult(content="查無符合的餐點。")
    lines = [f"{it['id']} | {it['name']} | ${it.get('price')}" for it in hits]
    return ToolResult(content="\n".join(lines))


register(ToolSpec(
    name="search_menu",
    description="依關鍵字、分類或別名搜尋菜單，回傳符合的餐點 ID、名稱與價格。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜尋關鍵字，例如『漢堡』『早餐』『可樂』"},
            "limit": {"type": "integer", "description": "最多回傳幾筆，預設 8"},
        },
        "required": ["query"],
    },
    handler=_search_menu,
))
```

- [ ] **Step 4: Write `app/tools/cart_tools.py`**

```python
from context import AgentContext
from domain import menu
from tools.registry import ToolResult, ToolSpec, register


def _add_to_cart(args: dict, ctx: AgentContext) -> ToolResult:
    item_id = str(args.get("item_id", "")).strip()
    qty = int(args.get("quantity", 1) or 1)
    item = menu.get_item(item_id)
    if item is None:
        return ToolResult(
            content=f"餐點 ID 不存在於菜單：{item_id}。請先用 search_menu 確認正確 ID。", ok=False)
    if qty < 1:
        return ToolResult(content="數量必須 ≥ 1。", ok=False)
    ctx.add_cart_action({"action": "add", "item_id": item_id, "name": item["name"], "quantity": qty})
    return ToolResult(content=f"已加入 {qty} 份 {item['name']}（{item_id}）。")


def _update_quantity(args: dict, ctx: AgentContext) -> ToolResult:
    item_id = str(args.get("item_id", "")).strip()
    qty = int(args.get("quantity", 1) or 1)
    item = menu.get_item(item_id)
    if item is None:
        return ToolResult(content=f"餐點 ID 不存在：{item_id}。", ok=False)
    ctx.add_cart_action({"action": "update", "item_id": item_id, "name": item["name"], "quantity": qty})
    return ToolResult(content=f"已將 {item['name']} 數量改為 {qty}。")


def _remove_from_cart(args: dict, ctx: AgentContext) -> ToolResult:
    item_id = str(args.get("item_id", "")).strip()
    item = menu.get_item(item_id)
    name = item["name"] if item else item_id
    ctx.add_cart_action({"action": "remove", "item_id": item_id, "name": name})
    return ToolResult(content=f"已移除 {name}。")


register(ToolSpec(
    name="add_to_cart",
    description="把指定菜單餐點加入購物車。item_id 必須是菜單中存在的 MCDxxx ID。",
    parameters={
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "菜單餐點 ID，格式 MCDxxx"},
            "quantity": {"type": "integer", "description": "數量，預設 1"},
        },
        "required": ["item_id"],
    },
    handler=_add_to_cart,
))

register(ToolSpec(
    name="update_quantity",
    description="修改購物車中某餐點的數量。",
    parameters={
        "type": "object",
        "properties": {
            "item_id": {"type": "string"},
            "quantity": {"type": "integer"},
        },
        "required": ["item_id", "quantity"],
    },
    handler=_update_quantity,
))

register(ToolSpec(
    name="remove_from_cart",
    description="從購物車移除某餐點。",
    parameters={
        "type": "object",
        "properties": {"item_id": {"type": "string"}},
        "required": ["item_id"],
    },
    handler=_remove_from_cart,
))
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_cart_tools.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/pos_agent
git add app/tools/menu_tools.py app/tools/cart_tools.py tests/test_cart_tools.py
git commit -m "feat: menu + cart tools with in-handler whitelist enforcement"
```

---

## Task 7: Recommend / staff / kb tools + builtin loader

**Files:**
- Create: `/home/oliver/pos_agent/app/tools/recommend_tools.py`
- Create: `/home/oliver/pos_agent/app/tools/staff_tools.py`
- Create: `/home/oliver/pos_agent/app/tools/kb_tools.py`
- Create: `/home/oliver/pos_agent/app/tools/builtin.py`
- Test: `/home/oliver/pos_agent/tests/test_recommend_tools.py`

- [ ] **Step 1: Write the failing test `tests/test_recommend_tools.py`**

```python
import tools.builtin  # noqa: F401  (registers every built-in tool on import)
from context import AgentContext
from tools import recommend_tools, staff_tools
from tools.registry import get_tool


def test_recommend_items_picks_from_whitelist(menu_file):
    res = recommend_tools._recommend_items({"n": 2}, AgentContext())
    assert res.ok is True
    assert res.content.count("\n") == 1     # 2 lines -> 1 newline
    assert "MCD" in res.content


def test_recommend_items_filters_by_category(menu_file):
    res = recommend_tools._recommend_items({"category": "飲料"}, AgentContext())
    assert "MCD120" in res.content and "MCD050" not in res.content


def test_escalate_to_staff_records_action():
    ctx = AgentContext()
    res = staff_tools._escalate_to_staff({"reason": "付款失敗"}, ctx)
    assert res.ok is True
    assert ctx.cart_actions[0] == {"action": "escalate_to_staff", "reason": "付款失敗"}


def test_builtin_registers_all_expected_tools():
    for name in ["search_menu", "add_to_cart", "update_quantity", "remove_from_cart",
                 "recommend_items", "query_kb", "escalate_to_staff"]:
        assert get_tool(name) is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_recommend_tools.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.builtin'`.

- [ ] **Step 3: Write `app/tools/recommend_tools.py`**

```python
from context import AgentContext
from domain import menu
from tools.registry import ToolResult, ToolSpec, register


def _recommend_items(args: dict, ctx: AgentContext) -> ToolResult:
    n = int(args.get("n", 3) or 3)
    category = str(args.get("category", "")).strip()
    items = menu.load_menu()
    if category:
        items = [it for it in items if it.get("category") == category]
    picks = items[:n]
    if not picks:
        return ToolResult(content="目前沒有可推薦的餐點。")
    lines = [f"{it['id']} | {it['name']} | ${it.get('price')}" for it in picks]
    return ToolResult(content="\n".join(lines))


register(ToolSpec(
    name="recommend_items",
    description="從菜單白名單推薦 n 個餐點，可選指定分類。",
    parameters={
        "type": "object",
        "properties": {
            "n": {"type": "integer", "description": "推薦數量，預設 3"},
            "category": {"type": "string", "description": "可選分類，例如『早餐』『主餐』『飲料』"},
        },
    },
    handler=_recommend_items,
))
```

- [ ] **Step 4: Write `app/tools/staff_tools.py`**

```python
from context import AgentContext
from tools.registry import ToolResult, ToolSpec, register


def _escalate_to_staff(args: dict, ctx: AgentContext) -> ToolResult:
    reason = str(args.get("reason", "")).strip() or "未指定原因"
    ctx.add_cart_action({"action": "escalate_to_staff", "reason": reason})
    return ToolResult(content=f"已通知服務人員（原因：{reason}）。")


register(ToolSpec(
    name="escalate_to_staff",
    description="通知真人服務人員前來協助。用於付款失敗、抱怨或顧客明確要求真人協助。",
    parameters={
        "type": "object",
        "properties": {"reason": {"type": "string", "description": "需要協助的原因"}},
        "required": ["reason"],
    },
    handler=_escalate_to_staff,
))
```

- [ ] **Step 5: Write `app/tools/kb_tools.py`**

```python
import config
from context import AgentContext
from tools.registry import ToolResult, ToolSpec, register


def _query_kb(args: dict, ctx: AgentContext) -> ToolResult:
    if not config.get("RAG_ENABLED", False):
        return ToolResult(content="（知識庫未啟用）")
    # 第一階段：RAG 尚未接，回空字串。後續階段接 fastembed 本地向量搜尋。
    return ToolResult(content="（知識庫查無資料）")


register(ToolSpec(
    name="query_kb",
    description="查詢餐廳知識庫（營業資訊、優惠、過敏原等）。",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    handler=_query_kb,
))
```

- [ ] **Step 6: Write `app/tools/builtin.py`**

```python
"""Import side-effect module: importing it registers every built-in tool.

Import this once at process start (main.py / cli.py) or in tests that need
the full tool set populated in the registry.
"""
from tools import (  # noqa: F401
    cart_tools,
    kb_tools,
    menu_tools,
    recommend_tools,
    staff_tools,
)
```

- [ ] **Step 7: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_recommend_tools.py -q`
Expected: PASS (4 passed).

- [ ] **Step 8: Commit**

```bash
cd /home/oliver/pos_agent
git add app/tools/recommend_tools.py app/tools/staff_tools.py app/tools/kb_tools.py app/tools/builtin.py tests/test_recommend_tools.py
git commit -m "feat: recommend/staff/kb tools + builtin tool loader"
```

---

## Task 8: Agent base loop

**Files:**
- Create: `/home/oliver/pos_agent/app/agents/base.py`
- Test: `/home/oliver/pos_agent/tests/test_agent_loop.py`

- [ ] **Step 1: Write the failing test `tests/test_agent_loop.py`**

```python
import tools.builtin  # noqa: F401
from agents.base import Agent, AgentResult
from context import AgentContext
from llm.fake_provider import FakeProvider
from llm.provider import LLMResponse, ToolCall


def test_agent_executes_tool_then_returns_text(menu_file):
    provider = FakeProvider([
        LLMResponse(tool_calls=[ToolCall(id="t1", name="add_to_cart",
                                         arguments={"item_id": "MCD050", "quantity": 1})]),
        LLMResponse(text="已為您加入大麥克。"),
    ])
    agent = Agent(provider, "sys", ["add_to_cart"], max_iters=5)
    ctx = AgentContext(session_id="s1")
    result = agent.run("我要大麥克", ctx)
    assert isinstance(result, AgentResult)
    assert result.ai_response == "已為您加入大麥克。"
    assert result.cart_actions[0]["item_id"] == "MCD050"
    assert result.trace[0] == {"tool": "add_to_cart",
                               "args": {"item_id": "MCD050", "quantity": 1}, "ok": True}


def test_agent_records_failed_tool_and_recovers(menu_file):
    provider = FakeProvider([
        LLMResponse(tool_calls=[ToolCall(id="t1", name="add_to_cart",
                                         arguments={"item_id": "MCD999"})]),
        LLMResponse(text="抱歉，找不到該餐點。"),
    ])
    agent = Agent(provider, "sys", ["add_to_cart"], max_iters=5)
    result = agent.run("亂點", AgentContext())
    assert result.trace[0]["ok"] is False
    assert result.cart_actions == []
    assert result.ai_response == "抱歉，找不到該餐點。"


def test_agent_unknown_tool_is_reported(menu_file):
    provider = FakeProvider([
        LLMResponse(tool_calls=[ToolCall(id="t1", name="nope", arguments={})]),
        LLMResponse(text="done"),
    ])
    agent = Agent(provider, "sys", ["add_to_cart"], max_iters=5)
    result = agent.run("x", AgentContext())
    assert result.trace[0] == {"tool": "nope", "args": {}, "ok": False}


def test_agent_max_iters_guard_returns_last_text(menu_file):
    # Provider always asks for a tool -> loop must stop at max_iters.
    provider = FakeProvider([
        LLMResponse(text="思考中", tool_calls=[ToolCall(id=f"t{i}", name="search_menu",
                                                        arguments={"query": "可樂"})])
        for i in range(10)
    ])
    agent = Agent(provider, "sys", ["search_menu"], max_iters=3)
    result = agent.run("loop", AgentContext())
    assert len(result.trace) == 3          # exactly max_iters tool rounds
    assert result.ai_response  # non-empty safe fallback
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_agent_loop.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.base'`.

- [ ] **Step 3: Write `app/agents/base.py`**

```python
from dataclasses import dataclass, field

from context import AgentContext
from llm.provider import Message
from tools import registry


@dataclass
class AgentResult:
    ai_response: str
    cart_actions: list = field(default_factory=list)
    trace: list = field(default_factory=list)


class Agent:
    def __init__(self, provider, system_prompt: str, tool_names: list[str], max_iters: int = 6):
        self.provider = provider
        self.system_prompt = system_prompt
        self.tool_names = tool_names
        self.max_iters = max_iters

    def _tools(self):
        return registry.get_tools(self.tool_names)

    def run(self, user_input: str, ctx: AgentContext) -> AgentResult:
        messages = [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=user_input),
        ]
        tools = self._tools()
        last_text = ""
        for _ in range(self.max_iters):
            resp = self.provider.run(messages, tools)
            last_text = resp.text or last_text
            messages.append(Message(role="assistant", content=resp.text, tool_calls=resp.tool_calls))
            if not resp.tool_calls:
                return AgentResult(
                    ai_response=resp.text,
                    cart_actions=ctx.drain_cart_actions(),
                    trace=ctx.trace,
                )
            for tc in resp.tool_calls:
                spec = registry.get_tool(tc.name)
                if spec is None:
                    content, ok = f"未知工具: {tc.name}", False
                else:
                    res = spec.handler(tc.arguments or {}, ctx)
                    content, ok = res.content, res.ok
                ctx.trace.append({"tool": tc.name, "args": tc.arguments, "ok": ok})
                messages.append(Message(role="tool", content=content, tool_call_id=tc.id))
        # MAX_ITERS guard: stop the loop, return what we have + a safe line.
        return AgentResult(
            ai_response=last_text or "需要協助嗎？我可以幫您點餐。",
            cart_actions=ctx.drain_cart_actions(),
            trace=ctx.trace,
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_agent_loop.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/agents/base.py tests/test_agent_loop.py
git commit -m "feat: Agent base tool-calling loop with max-iters guard"
```

---

## Task 9: Ollama provider

**Files:**
- Create: `/home/oliver/pos_agent/app/llm/ollama_provider.py`
- Test: `/home/oliver/pos_agent/tests/test_ollama_provider.py`

- [ ] **Step 1: Write the failing test `tests/test_ollama_provider.py`**

```python
import tools.builtin  # noqa: F401
from llm.ollama_provider import OllamaProvider, _msg_to_ollama, _tool_to_ollama
from llm.provider import Message, ToolCall
from tools.registry import get_tool


def test_tool_serialization_matches_ollama_schema():
    spec = get_tool("add_to_cart")
    out = _tool_to_ollama(spec)
    assert out["type"] == "function"
    assert out["function"]["name"] == "add_to_cart"
    assert out["function"]["parameters"]["properties"]["item_id"]["type"] == "string"


def test_assistant_tool_call_message_serialization():
    m = Message(role="assistant", content="",
                tool_calls=[ToolCall(id="x", name="search_menu", arguments={"query": "可樂"})])
    out = _msg_to_ollama(m)
    assert out["tool_calls"][0]["function"] == {"name": "search_menu", "arguments": {"query": "可樂"}}


def test_run_parses_tool_calls(monkeypatch):
    class FakeResp:
        def raise_for_status(self): pass
        def json(self):
            return {"message": {"content": "",
                                 "tool_calls": [{"function": {"name": "add_to_cart",
                                                              "arguments": {"item_id": "MCD050"}}}]}}

    captured = {}

    def fake_post(url, json, timeout):
        captured["payload"] = json
        return FakeResp()

    monkeypatch.setattr("llm.ollama_provider.requests.post", fake_post)
    resp = OllamaProvider().run([Message("user", "我要大麥克")], get_tools_for_test())
    assert resp.tool_calls[0].name == "add_to_cart"
    assert resp.tool_calls[0].arguments == {"item_id": "MCD050"}
    assert "tools" in captured["payload"]      # tools were sent


def test_run_parses_plain_text(monkeypatch):
    class FakeResp:
        def raise_for_status(self): pass
        def json(self):
            return {"message": {"content": "好的"}}

    monkeypatch.setattr("llm.ollama_provider.requests.post", lambda url, json, timeout: FakeResp())
    resp = OllamaProvider().run([Message("user", "hi")], [])
    assert resp.text == "好的" and resp.tool_calls == []


def get_tools_for_test():
    return [get_tool("add_to_cart")]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_ollama_provider.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm.ollama_provider'`.

- [ ] **Step 3: Write `app/llm/ollama_provider.py`**

```python
import json

import requests

import config
from llm.provider import LLMResponse, Message, ToolCall


def _tool_to_ollama(spec) -> dict:
    return {"type": "function", "function": {
        "name": spec.name, "description": spec.description, "parameters": spec.parameters}}


def _msg_to_ollama(m: Message) -> dict:
    d = {"role": m.role, "content": m.content or ""}
    if m.role == "assistant" and m.tool_calls:
        d["tool_calls"] = [{"function": {"name": tc.name, "arguments": tc.arguments}}
                           for tc in m.tool_calls]
    return d


class OllamaProvider:
    name = "ollama"

    def run(self, messages, tools) -> LLMResponse:
        payload = {
            "model": config.get("OLLAMA_MODEL", "qwen3.5:4b"),
            "messages": [_msg_to_ollama(m) for m in messages],
            "stream": False,
            "think": False,
            "options": {"temperature": float(config.get("LLM_TEMPERATURE", 0.7))},
        }
        if tools:
            payload["tools"] = [_tool_to_ollama(t) for t in tools]
        resp = requests.post(
            config.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api/chat"),
            json=payload, timeout=int(config.get("OLLAMA_TIMEOUT", 120)))
        resp.raise_for_status()
        msg = resp.json().get("message", {}) or {}
        tcs = []
        for i, raw in enumerate(msg.get("tool_calls") or []):
            fn = raw.get("function", {}) or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tcs.append(ToolCall(id=f"ollama-{i}", name=fn.get("name", ""), arguments=args))
        return LLMResponse(text=msg.get("content", "") or "", tool_calls=tcs)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_ollama_provider.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/llm/ollama_provider.py tests/test_ollama_provider.py
git commit -m "feat: Ollama provider with native tool-calling normalization"
```

---

## Task 10: Claude provider

**Files:**
- Create: `/home/oliver/pos_agent/app/llm/claude_provider.py`
- Test: `/home/oliver/pos_agent/tests/test_claude_provider.py`

> The SDK call itself is integration-only. We TDD the pure conversion function `_to_anthropic_messages` and the tool-schema converter, which carry all the tricky logic.

- [ ] **Step 1: Write the failing test `tests/test_claude_provider.py`**

```python
import tools.builtin  # noqa: F401
from llm.claude_provider import _to_anthropic_messages, _tool_to_anthropic
from llm.provider import Message, ToolCall
from tools.registry import get_tool


def test_tool_to_anthropic_uses_input_schema():
    out = _tool_to_anthropic(get_tool("add_to_cart"))
    assert out["name"] == "add_to_cart"
    assert "input_schema" in out
    assert out["input_schema"]["properties"]["item_id"]["type"] == "string"


def test_system_messages_collected_separately():
    system, msgs = _to_anthropic_messages([
        Message("system", "你是助理"),
        Message("user", "我要可樂"),
    ])
    assert system == "你是助理"
    assert msgs == [{"role": "user", "content": "我要可樂"}]


def test_assistant_tool_use_becomes_blocks():
    _, msgs = _to_anthropic_messages([
        Message("assistant", "稍等", tool_calls=[ToolCall(id="tu1", name="search_menu",
                                                          arguments={"query": "可樂"})]),
    ])
    blocks = msgs[0]["content"]
    assert {"type": "text", "text": "稍等"} in blocks
    assert {"type": "tool_use", "id": "tu1", "name": "search_menu",
            "input": {"query": "可樂"}} in blocks


def test_tool_result_attaches_as_user_block():
    _, msgs = _to_anthropic_messages([
        Message("assistant", "", tool_calls=[ToolCall(id="tu1", name="search_menu", arguments={})]),
        Message("tool", "MCD120 | 可口可樂", tool_call_id="tu1"),
    ])
    # last message is a user message carrying the tool_result block
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"][0] == {
        "type": "tool_result", "tool_use_id": "tu1", "content": "MCD120 | 可口可樂"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_claude_provider.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm.claude_provider'`.

- [ ] **Step 3: Write `app/llm/claude_provider.py`**

```python
import config
from llm.provider import LLMResponse, ToolCall


def _tool_to_anthropic(spec) -> dict:
    return {"name": spec.name, "description": spec.description, "input_schema": spec.parameters}


def _to_anthropic_messages(messages):
    """Return (system_text, anthropic_messages). System messages are merged
    into the `system` param; tool results attach as tool_result blocks on a
    user message (merged onto the preceding user block list when possible).
    """
    system_parts = []
    out = []
    for m in messages:
        if m.role == "system":
            if m.content:
                system_parts.append(m.content)
        elif m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            blocks = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
            out.append({"role": "assistant", "content": blocks if blocks else (m.content or "")})
        elif m.role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id or "", "content": m.content}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
    return "\n\n".join(system_parts), out


class ClaudeProvider:
    name = "claude"

    def __init__(self):
        import anthropic
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY or None)

    def run(self, messages, tools) -> LLMResponse:
        system, msgs = _to_anthropic_messages(messages)
        kwargs = {
            "model": config.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
            "max_tokens": int(config.get("LLM_MAX_TOKENS", 512)),
            "system": system,
            "messages": msgs,
        }
        if tools:
            kwargs["tools"] = [_tool_to_anthropic(t) for t in tools]
        resp = self._client.messages.create(**kwargs)
        text, tcs = "", []
        for block in resp.content:
            btype = getattr(block, "type", "")
            if btype == "text":
                text += getattr(block, "text", "")
            elif btype == "tool_use":
                tcs.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {})))
        return LLMResponse(text=text, tool_calls=tcs)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_claude_provider.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/llm/claude_provider.py tests/test_claude_provider.py
git commit -m "feat: Claude provider with message/tool conversion (TDD on converters)"
```

---

## Task 11: Gemini provider

**Files:**
- Create: `/home/oliver/pos_agent/app/llm/gemini_provider.py`
- Test: `/home/oliver/pos_agent/tests/test_gemini_provider.py`

> SDK call is integration-only. We TDD the tool-declaration converter and the response parser (using duck-typed fakes that mimic `google-genai` objects).

- [ ] **Step 1: Write the failing test `tests/test_gemini_provider.py`**

```python
import types as _t

import tools.builtin  # noqa: F401
from llm.gemini_provider import _parse_gemini_response, _tool_to_gemini_decl
from tools.registry import get_tool


def test_tool_decl_shape():
    out = _tool_to_gemini_decl(get_tool("add_to_cart"))
    assert out["name"] == "add_to_cart"
    assert out["parameters"]["properties"]["item_id"]["type"] == "string"


def _fake_response(parts):
    candidate = _t.SimpleNamespace(content=_t.SimpleNamespace(parts=parts))
    return _t.SimpleNamespace(candidates=[candidate])


def test_parse_function_call_part():
    fc = _t.SimpleNamespace(name="add_to_cart", args={"item_id": "MCD050"})
    part = _t.SimpleNamespace(function_call=fc, text="")
    resp = _parse_gemini_response(_fake_response([part]))
    assert resp.tool_calls[0].name == "add_to_cart"
    assert resp.tool_calls[0].arguments == {"item_id": "MCD050"}


def test_parse_text_part():
    part = _t.SimpleNamespace(function_call=None, text="好的，已處理。")
    resp = _parse_gemini_response(_fake_response([part]))
    assert resp.text == "好的，已處理。" and resp.tool_calls == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_gemini_provider.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm.gemini_provider'`.

- [ ] **Step 3: Write `app/llm/gemini_provider.py`**

```python
import config
from llm.provider import LLMResponse, ToolCall


def _tool_to_gemini_decl(spec) -> dict:
    return {"name": spec.name, "description": spec.description, "parameters": spec.parameters}


def _parse_gemini_response(response) -> LLMResponse:
    text, tcs = "", []
    try:
        parts = response.candidates[0].content.parts
    except Exception:
        return LLMResponse(text=getattr(response, "text", "") or "")
    for i, part in enumerate(parts):
        fc = getattr(part, "function_call", None)
        if fc and getattr(fc, "name", ""):
            args = dict(getattr(fc, "args", {}) or {})
            tcs.append(ToolCall(id=f"gemini-{i}", name=fc.name, arguments=args))
        elif getattr(part, "text", ""):
            text += part.text
    return LLMResponse(text=text, tool_calls=tcs)


class GeminiProvider:
    name = "gemini"

    def __init__(self):
        from google import genai
        kwargs = {}
        if config.GEMINI_API_KEY:
            kwargs["api_key"] = config.GEMINI_API_KEY
        self._client = genai.Client(**kwargs)

    def run(self, messages, tools) -> LLMResponse:
        from google.genai import types
        system_parts = [m.content for m in messages if m.role == "system" and m.content]
        contents = self._to_contents(messages, types)
        cfg = types.GenerateContentConfig(
            temperature=float(config.get("LLM_TEMPERATURE", 0.7)),
            max_output_tokens=int(config.get("LLM_MAX_TOKENS", 512)),
            system_instruction="\n\n".join(system_parts) or None,
        )
        if tools:
            cfg.tools = [types.Tool(
                function_declarations=[_tool_to_gemini_decl(t) for t in tools])]
        resp = self._client.models.generate_content(
            model=config.get("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=contents, config=cfg)
        return _parse_gemini_response(resp)

    def _to_contents(self, messages, types):
        contents = []
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=m.content)]))
            elif m.role == "assistant":
                parts = []
                if m.content:
                    parts.append(types.Part(text=m.content))
                for tc in m.tool_calls:
                    parts.append(types.Part(function_call=types.FunctionCall(
                        name=tc.name, args=tc.arguments)))
                contents.append(types.Content(role="model", parts=parts or [types.Part(text="")]))
            elif m.role == "tool":
                contents.append(types.Content(role="user", parts=[types.Part(
                    function_response=types.FunctionResponse(
                        name=m.tool_call_id or "tool", response={"content": m.content}))]))
        return contents
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_gemini_provider.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/llm/gemini_provider.py tests/test_gemini_provider.py
git commit -m "feat: Gemini provider with function-calling normalization (TDD on converters)"
```

---

## Task 12: Provider factory + fallback

**Files:**
- Create: `/home/oliver/pos_agent/app/llm/factory.py`
- Test: `/home/oliver/pos_agent/tests/test_factory.py`

- [ ] **Step 1: Write the failing test `tests/test_factory.py`**

```python
import pytest

from llm import factory
from llm.provider import LLMResponse, Message


class _Boom:
    name = "boom"
    def run(self, messages, tools):
        raise RuntimeError("primary down")


class _OK:
    name = "ok"
    def run(self, messages, tools):
        return LLMResponse(text="fallback-ok")


def test_get_provider_caches_instances(monkeypatch):
    factory._PROVIDERS.clear()
    monkeypatch.setattr(factory, "_build", lambda name: _OK())
    p1 = factory.get_provider("ollama")
    p2 = factory.get_provider("ollama")
    assert p1 is p2


def test_fallback_runs_secondary_on_error():
    fb = factory.FallbackProvider(_Boom(), _OK())
    out = fb.run([Message("user", "hi")], [])
    assert out.text == "fallback-ok"


def test_get_provider_with_fallback_no_wrap_when_same(monkeypatch):
    factory._PROVIDERS.clear()
    monkeypatch.setattr(factory, "_build", lambda name: _OK())
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "ollama")
    prov = factory.get_provider_with_fallback()
    assert not isinstance(prov, factory.FallbackProvider)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_factory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm.factory'`.

- [ ] **Step 3: Write `app/llm/factory.py`**

```python
import config

_PROVIDERS = {}


def _build(name: str):
    """Lazily import provider SDKs so a missing SDK only breaks that provider."""
    name = (name or "").lower()
    if name == "claude":
        from llm.claude_provider import ClaudeProvider
        return ClaudeProvider()
    if name == "gemini":
        from llm.gemini_provider import GeminiProvider
        return GeminiProvider()
    from llm.ollama_provider import OllamaProvider
    return OllamaProvider()


def get_provider(name: str | None = None):
    key = (name or config.get("LLM_PROVIDER", "ollama")).lower()
    if key not in _PROVIDERS:
        _PROVIDERS[key] = _build(key)
    return _PROVIDERS[key]


class FallbackProvider:
    """Wraps a primary provider; on any exception, retries with the secondary."""
    def __init__(self, primary, secondary):
        self.primary = primary
        self.secondary = secondary
        self.name = f"{primary.name}->{secondary.name}"

    def run(self, messages, tools):
        try:
            return self.primary.run(messages, tools)
        except Exception as e:
            print(f"⚠️ provider {self.primary.name} 失敗，fallback {self.secondary.name}: {e}")
            return self.secondary.run(messages, tools)


def get_provider_with_fallback():
    primary = get_provider(config.get("LLM_PROVIDER", "ollama"))
    fb_name = str(config.get("LLM_FALLBACK_PROVIDER", "ollama")).lower()
    if primary.name == fb_name:
        return primary
    return FallbackProvider(primary, get_provider(fb_name))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_factory.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/llm/factory.py tests/test_factory.py
git commit -m "feat: provider factory with caching + fallback wrapper"
```

---

## Task 13: Prompts + four agents (router orchestrator)

**Files:**
- Create: `/home/oliver/pos_agent/app/prompts/defaults.py`
- Create: `/home/oliver/pos_agent/app/agents/ordering_agent.py`
- Create: `/home/oliver/pos_agent/app/agents/recommendation_agent.py`
- Create: `/home/oliver/pos_agent/app/agents/intervention_agent.py`
- Create: `/home/oliver/pos_agent/app/agents/orchestrator.py`
- Test: `/home/oliver/pos_agent/tests/test_agents.py`

- [ ] **Step 1: Write the failing test `tests/test_agents.py`**

```python
import tools.builtin  # noqa: F401
from agents import orchestrator
from agents.ordering_agent import build_ordering_agent
from context import AgentContext
from llm.fake_provider import FakeProvider
from llm.provider import LLMResponse, ToolCall


def test_build_ordering_agent_has_cart_tools(menu_file):
    agent = build_ordering_agent(FakeProvider([]))
    assert "add_to_cart" in agent.tool_names and "search_menu" in agent.tool_names


def test_route_parses_json(menu_file):
    provider = FakeProvider([LLMResponse(text='{"route": "recommendation"}')])
    assert orchestrator.route("不知道吃什麼", provider) == "recommendation"


def test_route_defaults_to_ordering_on_bad_json(menu_file):
    provider = FakeProvider([LLMResponse(text="not json")])
    assert orchestrator.route("x", provider) == "ordering"


def test_handle_routes_to_ordering_and_runs_tools(menu_file):
    # 1st response = router decision, 2nd = tool call, 3rd = final text
    provider = FakeProvider([
        LLMResponse(text='{"route": "ordering"}'),
        LLMResponse(tool_calls=[ToolCall(id="t1", name="add_to_cart",
                                         arguments={"item_id": "MCD050", "quantity": 1})]),
        LLMResponse(text="已為您加入大麥克。"),
    ])
    result = orchestrator.handle("我要大麥克", AgentContext(), provider)
    assert result.ai_response == "已為您加入大麥克。"
    assert result.cart_actions[0]["item_id"] == "MCD050"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_agents.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.ordering_agent'`.

- [ ] **Step 3: Write `app/prompts/defaults.py`**

```python
ORCHESTRATOR_ROUTER_PROMPT = """你是麥當勞自助點餐機的總調度。判斷顧客輸入屬於哪一類，\
只輸出一個 JSON 物件：{"route": "ordering" | "recommendation" | "general"}。
- ordering：點餐、加入購物車、修改數量、詢問特定餐點。
- recommendation：要推薦、不知道吃什麼、選擇困難。
- general：其他一般問題。
只輸出 JSON，不要其他文字。"""

ORDERING_PROMPT = """你是麥當勞點餐助理。用工具協助顧客點餐：
- 先用 search_menu 查餐點，確認正確的 MCDxxx ID 後，才能用 add_to_cart。
- 絕對不要自己編造餐點名稱或 ID；ID 必須來自 search_menu 的結果。
- 完成後用繁體中文簡短回覆顧客你做了什麼。"""

RECOMMENDATION_PROMPT = """你是麥當勞推薦助理。用 recommend_items 從菜單挑選餐點，\
用繁體中文給顧客 1-3 個推薦與一句促購短語。不要編造菜單沒有的餐點。"""

INTERVENTION_PROMPT = """你是自助點餐機的互動協助判斷助理。根據顧客的操作事件判斷是否需要介入：
- 若偵測到付款失敗或顧客抱怨，使用 escalate_to_staff 通知真人。
- 否則用繁體中文給一句友善的協助提示。"""
```

- [ ] **Step 4: Write `app/agents/ordering_agent.py`**

```python
import config
from agents.base import Agent
from llm import factory
from prompts import defaults


def build_ordering_agent(provider=None) -> Agent:
    return Agent(
        provider=provider or factory.get_provider_with_fallback(),
        system_prompt=defaults.ORDERING_PROMPT,
        tool_names=["search_menu", "add_to_cart", "update_quantity", "remove_from_cart", "query_kb"],
        max_iters=int(config.get("AGENT_MAX_ITERS", 6)),
    )
```

- [ ] **Step 5: Write `app/agents/recommendation_agent.py`**

```python
import config
from agents.base import Agent
from llm import factory
from prompts import defaults


def build_recommendation_agent(provider=None) -> Agent:
    return Agent(
        provider=provider or factory.get_provider_with_fallback(),
        system_prompt=defaults.RECOMMENDATION_PROMPT,
        tool_names=["recommend_items", "search_menu"],
        max_iters=int(config.get("AGENT_MAX_ITERS", 6)),
    )
```

- [ ] **Step 6: Write `app/agents/intervention_agent.py`**

```python
import config
from agents.base import Agent
from llm import factory
from prompts import defaults


def build_intervention_agent(provider=None) -> Agent:
    return Agent(
        provider=provider or factory.get_provider_with_fallback(),
        system_prompt=defaults.INTERVENTION_PROMPT,
        tool_names=["escalate_to_staff", "recommend_items"],
        max_iters=int(config.get("AGENT_MAX_ITERS", 6)),
    )
```

- [ ] **Step 7: Write `app/agents/orchestrator.py`**

```python
import json

from agents.base import AgentResult
from agents.ordering_agent import build_ordering_agent
from agents.recommendation_agent import build_recommendation_agent
from context import AgentContext
from llm import factory
from llm.provider import Message
from prompts import defaults

_VALID_ROUTES = {"ordering", "recommendation", "general"}


def route(user_input: str, provider=None) -> str:
    provider = provider or factory.get_provider_with_fallback()
    resp = provider.run(
        [Message("system", defaults.ORCHESTRATOR_ROUTER_PROMPT), Message("user", user_input)],
        [],
    )
    try:
        r = str(json.loads(resp.text).get("route", "")).strip()
    except Exception:
        r = ""
    return r if r in _VALID_ROUTES else "ordering"


def handle(user_input: str, ctx: AgentContext, provider=None) -> AgentResult:
    provider = provider or factory.get_provider_with_fallback()
    decision = route(user_input, provider)
    if decision == "recommendation":
        agent = build_recommendation_agent(provider)
    else:
        agent = build_ordering_agent(provider)   # ordering handles general too
    return agent.run(user_input, ctx)
```

- [ ] **Step 8: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_agents.py -q`
Expected: PASS (4 passed).

- [ ] **Step 9: Commit**

```bash
cd /home/oliver/pos_agent
git add app/prompts/defaults.py app/agents/ordering_agent.py app/agents/recommendation_agent.py app/agents/intervention_agent.py app/agents/orchestrator.py tests/test_agents.py
git commit -m "feat: prompts + four agents with router-style orchestrator"
```

---

## Task 14: FastAPI app + routes

**Files:**
- Create: `/home/oliver/pos_agent/app/api/chat_routes.py`
- Create: `/home/oliver/pos_agent/app/api/menu_routes.py`
- Create: `/home/oliver/pos_agent/app/api/event_routes.py`
- Create: `/home/oliver/pos_agent/app/main.py`
- Test: `/home/oliver/pos_agent/tests/test_api.py`

- [ ] **Step 1: Write the failing test `tests/test_api.py`**

```python
from fastapi.testclient import TestClient

import tools.builtin  # noqa: F401
from llm import factory
from llm.fake_provider import FakeProvider
from llm.provider import LLMResponse, ToolCall


def _client():
    from main import app
    return TestClient(app)


def test_health():
    assert _client().get("/health").json()["status"] == "ok"


def test_menu_endpoint(menu_file):
    data = _client().get("/api/menu").json()
    assert any(it["id"] == "MCD050" for it in data)


def test_chat_runs_agent(monkeypatch, menu_file):
    fake = FakeProvider([
        LLMResponse(text='{"route": "ordering"}'),
        LLMResponse(tool_calls=[ToolCall(id="t1", name="add_to_cart",
                                         arguments={"item_id": "MCD050", "quantity": 1})]),
        LLMResponse(text="已為您加入大麥克。"),
    ])
    monkeypatch.setattr(factory, "get_provider_with_fallback", lambda: fake)
    resp = _client().post("/api/chat", json={"session_id": "s1", "message": "我要大麥克"})
    body = resp.json()
    assert body["ai_response"] == "已為您加入大麥克。"
    assert body["cart_actions"][0]["item_id"] == "MCD050"


def test_interaction_event_triggers_intervention(monkeypatch, menu_file):
    fake = FakeProvider([
        LLMResponse(tool_calls=[ToolCall(id="t1", name="escalate_to_staff",
                                         arguments={"reason": "付款失敗"})]),
        LLMResponse(text="已通知服務人員。"),
    ])
    monkeypatch.setattr(factory, "get_provider_with_fallback", lambda: fake)
    resp = _client().post("/api/interaction_event",
                          json={"session_id": "s1", "event_type": "payment_fail", "detail": "卡關"})
    body = resp.json()
    assert body["actions"][0]["action"] == "escalate_to_staff"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_api.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'main'`.

- [ ] **Step 3: Write `app/api/chat_routes.py`**

```python
from fastapi import APIRouter
from pydantic import BaseModel

from agents import orchestrator
from context import AgentContext

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str = "anonymous"
    message: str


@router.post("/chat")
def chat(req: ChatRequest):
    ctx = AgentContext(session_id=req.session_id)
    result = orchestrator.handle(req.message, ctx)
    return {
        "ai_response": result.ai_response,
        "cart_actions": result.cart_actions,
        "trace": result.trace,
    }
```

- [ ] **Step 4: Write `app/api/menu_routes.py`**

```python
from fastapi import APIRouter

from domain import menu

router = APIRouter()


@router.get("/menu")
def get_menu():
    return menu.load_menu()
```

- [ ] **Step 5: Write `app/api/event_routes.py`**

```python
from fastapi import APIRouter
from pydantic import BaseModel

from agents.intervention_agent import build_intervention_agent
from context import AgentContext

router = APIRouter()


class EventRequest(BaseModel):
    session_id: str = "anonymous"
    event_type: str = ""
    detail: str = ""


def _run_intervention(req: "EventRequest") -> dict:
    ctx = AgentContext(session_id=req.session_id)
    agent = build_intervention_agent()
    result = agent.run(f"事件類型：{req.event_type}。細節：{req.detail}", ctx)
    return {"ai_response": result.ai_response, "actions": result.cart_actions, "trace": result.trace}


@router.post("/interaction_event")
def interaction_event(req: EventRequest):
    return _run_intervention(req)


@router.post("/barrier_state")
def barrier_state(req: EventRequest):
    return _run_intervention(req)
```

- [ ] **Step 6: Write `app/main.py`**

```python
import config
import tools.builtin  # noqa: F401  register all tools at startup
from api import chat_routes, event_routes, menu_routes
from fastapi import FastAPI

app = FastAPI(title="pos_agent")
app.include_router(chat_routes.router, prefix="/api")
app.include_router(menu_routes.router, prefix="/api")
app.include_router(event_routes.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "provider": config.get("LLM_PROVIDER", "ollama")}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

- [ ] **Step 7: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && python -m pytest tests/test_api.py -q`
Expected: PASS (4 passed).

- [ ] **Step 8: Run the full suite**

Run: `cd /home/oliver/pos_agent && python -m pytest -q`
Expected: PASS (all tests, ~36 passed).

- [ ] **Step 9: Commit**

```bash
cd /home/oliver/pos_agent
git add app/api/chat_routes.py app/api/menu_routes.py app/api/event_routes.py app/main.py tests/test_api.py
git commit -m "feat: FastAPI app with /api/chat, /api/menu, event endpoints"
```

---

## Task 15: CLI harness

**Files:**
- Create: `/home/oliver/pos_agent/cli.py`

> The CLI is interactive (reads stdin), so it isn't unit-tested. We verify it imports and wires up cleanly with a piped `exit`.

- [ ] **Step 1: Write `cli.py`**

```python
"""Interactive CLI to exercise the agent core without any UI.

Usage:  cd /home/oliver/pos_agent && python cli.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import tools.builtin  # noqa: E402,F401  register all tools
from agents import orchestrator  # noqa: E402
from context import AgentContext  # noqa: E402


def main():
    ctx = AgentContext(session_id="cli")
    print("pos_agent CLI — 輸入點餐需求，輸入 exit 離開")
    while True:
        try:
            text = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in {"exit", "quit", ""}:
            break
        result = orchestrator.handle(text, ctx)
        print(f"AI> {result.ai_response}")
        if result.cart_actions:
            print(f"    [動作] {result.cart_actions}")
        if result.trace:
            print(f"    [工具] {[t['tool'] for t in result.trace]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the CLI imports and exits cleanly**

Run: `cd /home/oliver/pos_agent && echo "exit" | python cli.py`
Expected: prints the banner `pos_agent CLI — 輸入點餐需求，輸入 exit 離開` and exits with code 0 (no import errors). It does NOT call any LLM because input is `exit`.

- [ ] **Step 3: Commit**

```bash
cd /home/oliver/pos_agent
git add cli.py
git commit -m "feat: interactive CLI harness for the agent core"
```

---

## Task 16: CLAUDE.md + README

**Files:**
- Create: `/home/oliver/pos_agent/CLAUDE.md`
- Create: `/home/oliver/pos_agent/README.md`

- [ ] **Step 1: Write `CLAUDE.md`**

````markdown
# pos_agent — 多 Agent 自助點餐核心

## 專案概述

Project_2026 的 AI agent 重構版。功能相仿（語音/文字點餐、推薦、互動介入），\
但底層從「固定 pipeline + 單次 LLM 強制 JSON」改為 **multi-agent + tool-calling**：\
LLM 主動持有工具、多步推理、自行決定呼叫哪個工具。

第一階段聚焦 agent 核心 + 最小 API（文字 `/api/chat` + CLI 驗證）。\
POS/admin UI、Emotion-LLaMA、WebSocket、完整 RAG、語音 `/api/ask` 為後續階段。

## Tech Stack

| 層 | 技術 |
|---|---|
| 後端 | Python 3.x、FastAPI（port 8000） |
| LLM | 可切換 provider：Ollama（本地，預設）/ Claude / Gemini |
| Tool-calling | 統一 ToolSpec → 各 provider adapter 正規化 |
| 資料 | JSON 檔（menu.json） |
| 測試 | pytest + FakeProvider（無需真實 LLM） |

## 啟動方式

```bash
cd /home/oliver/pos_agent
pip install -r requirements.txt
cp .env.example .env          # 填入 ANTHROPIC_API_KEY / GEMINI_API_KEY（用 ollama 可留空）

# 跑測試（不需任何 LLM）
python -m pytest -q

# CLI 互動測試
python cli.py

# 起服務
python app/main.py            # http://127.0.0.1:8000  （/health, /api/chat, /api/menu）
```

切換 provider：設定 `LLM_PROVIDER=ollama|claude|gemini`（環境變數或 `data/settings.json`）。\
雲端 provider 失敗時自動 fallback 到 `LLM_FALLBACK_PROVIDER`（預設 ollama）。

## 架構規則（修改前必讀）

### 三層抽象
- **llm/**：provider 抽象。`provider.py` 定義 `Message/ToolCall/LLMResponse/LLMProvider`。\
  每個 `*_provider.py` 把該 SDK 的 tool-calling 正規化成 `run(messages, tools) -> LLMResponse`。\
  新增 provider 只動 `llm/`，不影響 agents/tools。
- **tools/**：`registry.py` 定義 `ToolSpec`（name + description + JSON schema + handler）。\
  工具 handler 接 `(args, ctx)`、回 `ToolResult`，**直接 mutate `ctx`**（不靠 LLM 回傳結構）。\
  新工具 = 新 `*_tools.py` + 在 `builtin.py` 匯入。
- **agents/**：`base.Agent` 跑 tool-calling 迴圈。每個 agent = provider + system prompt + 工具子集。

### 不可違反的原則（沿用 Project_2026）
- **菜單白名單**：餐點一律來自 `data/menu.json`（ID 格式 `MCDxxx`）。\
  白名單**在 `add_to_cart` 等 handler 內強制**，LLM 不可幻覺餐點。
- **checkout 永遠可完成**，不加阻擋邏輯。
- **讀設定統一用 `config.get("KEY")`**，不要直接讀 `os.getenv`。
- 高風險介入（付款失敗、抱怨）走確定性工具（`escalate_to_staff`），不純靠 LLM 判斷。

### 分層職責
- **api/**：只解析請求 + 呼叫 agent + 回傳。不放業務邏輯。
- **agents/ + tools/**：業務邏輯。
- **domain/**：資料存取與白名單（`menu.py`）。

## 測試

- **FakeProvider**（`llm/fake_provider.py`）：餵腳本化 `LLMResponse`，讓 agent loop 在無真實 LLM 下確定性測試。
- 真實 provider（Claude/Gemini）只單元測試「訊息/工具轉換」純函式，SDK 呼叫為 integration（不在 CI 跑）。
- 跑全部：`python -m pytest -q`。

## 目錄

```
app/
├── config.py        設定（env > settings.json > 預設）
├── context.py       AgentContext（cart/history/mood/trace + cart_actions buffer）
├── main.py          FastAPI 入口
├── domain/menu.py   菜單載入 + 白名單
├── llm/             provider 抽象 + ollama/claude/gemini + factory + fake
├── tools/           registry + menu/cart/recommend/staff/kb + builtin
├── agents/          base + ordering/recommendation/intervention/orchestrator
├── prompts/         各 agent system prompt
└── api/             chat / menu / event 路由
data/menu.json       菜單（從 Project_2026 複製）
cli.py               互動測試器
tests/               pytest（FakeProvider）
```

## 後續階段（尚未實作）
- 語音 `/api/ask`（STT→orchestrator→TTS）
- POS / admin 前端、WebSocket 即時介入推送
- Emotion-LLaMA 事件情緒分析、完整 RAG（fastembed）、心情星星 context
````

- [ ] **Step 2: Write `README.md`**

```markdown
# pos_agent

Project_2026 的 multi-agent 重構版自助點餐後端。

詳細架構與規則見 [CLAUDE.md](./CLAUDE.md)。

## 快速開始

```bash
pip install -r requirements.txt
python -m pytest -q     # 測試（不需 LLM）
python cli.py           # CLI 互動測試
python app/main.py      # 起 API 服務 (http://127.0.0.1:8000)
```

## Provider 切換

| 環境變數 | 說明 |
|---|---|
| `LLM_PROVIDER` | `ollama`（預設）/ `claude` / `gemini` |
| `LLM_FALLBACK_PROVIDER` | 雲端失敗時的後備（預設 `ollama`） |
| `ANTHROPIC_API_KEY` | Claude 金鑰 |
| `GEMINI_API_KEY` | Gemini 金鑰 |
```

- [ ] **Step 3: Commit**

```bash
cd /home/oliver/pos_agent
git add CLAUDE.md README.md
git commit -m "docs: add CLAUDE.md and README for pos_agent"
```

---

## Final Verification

- [ ] **Run the full test suite**

Run: `cd /home/oliver/pos_agent && python -m pytest -q`
Expected: all tests pass (~36 passed, 0 failed).

- [ ] **Smoke-test the server boots** (no real LLM call needed for /health and /api/menu)

```bash
cd /home/oliver/pos_agent && PYTHONPATH=app python -c "from main import app; print('app routes:', sorted(r.path for r in app.routes if hasattr(r,'path')))"
```
Expected: includes `/health`, `/api/chat`, `/api/menu`, `/api/interaction_event`, `/api/barrier_state`.

---

## Notes for the Implementer

- **Why handlers mutate `ctx` instead of the LLM emitting `cart_actions`:** this is the core agent shift from Project_2026. The whitelist lives inside `add_to_cart`, so the LLM physically cannot add a non-menu item — it can only request one and get a rejection it must recover from.
- **Why the orchestrator is a router, not nested agent-as-tool:** weak local models (qwen3.5:4b) are unreliable at deep nested tool use, and a kiosk wants low latency/determinism. One classify call → delegate to one sub-agent. The seam to upgrade to agent-as-tool later is `orchestrator.handle`.
- **Provider parity is tested at the converter level**, not via live SDK calls — keep new provider logic in pure functions (`_to_anthropic_messages`, `_parse_gemini_response`, etc.) so it stays unit-testable.
- **Event endpoints bypass the orchestrator LLM** by design (latency) — they construct the intervention agent directly.
