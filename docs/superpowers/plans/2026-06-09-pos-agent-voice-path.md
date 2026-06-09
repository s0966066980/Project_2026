# pos_agent Stage 2 — Voice Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-streaming voice ordering path (`POST /api/ask`: 音訊 → STT → orchestrator → TTS) on top of the existing pos_agent core, with JSON session memory shared by voice and text, and zh/en auto-detection.

**Architecture:** A new `voice/` package holds STT/TTS provider abstractions (ABC + config-switched factory, lazy SDK import, plus deterministic fakes) and a `pipeline.handle_voice` orchestrator. `domain/session.py` persists conversation turns as JSON. `Agent.run` is extended to inject `ctx.history` as a text preamble and an English directive when `ctx.lang == "en"`. Both `/api/ask` and the existing `/api/chat` load/save the same session.

**Tech Stack:** Python, FastAPI (multipart upload), faster-whisper (STT, integration-only), edge-tts (TTS, integration-only), pytest with `asyncio.run()` for async unit tests + FakeSTT/FakeTTS/FakeProvider for determinism.

---

## File Structure

```
app/
├── config.py                 ← MODIFY (Task 1): add STT/TTS/session defaults
├── context.py                ← MODIFY (Task 2): add lang field
├── agents/base.py            ← MODIFY (Task 2): history + lang injection
├── domain/session.py         ← CREATE (Task 3): JSON session store
├── voice/
│   ├── __init__.py           ← CREATE (Task 4)
│   ├── stt.py                ← CREATE (Task 4): STTProvider + FasterWhisperSTT + get_stt
│   ├── tts.py                ← CREATE (Task 4): TTSProvider + EdgeTTSProvider + get_tts
│   ├── fakes.py              ← CREATE (Task 4): FakeSTT / FakeTTS
│   └── pipeline.py           ← CREATE (Task 5): handle_voice()
├── api/voice_routes.py       ← CREATE (Task 6): POST /api/ask
├── api/chat_routes.py        ← MODIFY (Task 7): session memory
├── main.py                   ← MODIFY (Task 6): mount voice router
└── CLAUDE.md                 ← MODIFY (Task 8)
tests/
├── test_config.py            ← CREATE (Task 1)
├── test_context.py           ← MODIFY (Task 2): lang default
├── test_agent_loop.py        ← MODIFY (Task 2): history + lang injection
├── test_session.py           ← CREATE (Task 3)
├── test_voice_providers.py   ← CREATE (Task 4)
├── test_voice_pipeline.py    ← CREATE (Task 5)
├── test_voice_api.py         ← CREATE (Task 6)
└── test_api.py               ← MODIFY (Task 7): chat session memory
```

> **Conventions (all tasks):** `app/` is the source root (pytest `pythonpath=["app"]`), bare imports (`import config`, `from domain import session`). Run tests with the conda env that has fastapi: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest -q` (or `/home/oliver/anaconda3/envs/emotion_ui/bin/python3 -m pytest -q`). Async unit tests use `asyncio.run(...)` in plain sync test functions — do NOT add pytest-asyncio. Every commit message ends with a trailing line: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. All git commands assume cwd `/home/oliver/pos_agent`. Stage-1 baseline is 51 passing tests.

---

## Task 1: Config defaults for STT/TTS/session

**Files:**
- Modify: `/home/oliver/pos_agent/app/config.py`
- Test: `/home/oliver/pos_agent/tests/test_config.py`

- [ ] **Step 1: Write the failing test `tests/test_config.py`**

```python
import config


def test_voice_defaults_present():
    assert config.get("STT_PROVIDER") == "faster_whisper"
    assert config.get("TTS_PROVIDER") == "edge"
    assert config.get("STT_MODEL") == "small"
    assert config.get("EDGE_TTS_VOICE") == "zh-TW-HsiaoChenNeural"
    assert config.get("EDGE_TTS_VOICE_EN") == "en-US-JennyNeural"
    assert int(config.get("VOICE_HISTORY_MAX_TURNS")) == 4
    assert str(config.get("SESSION_DIR")).endswith("data/sessions")


def test_stt_language_default_is_empty():
    assert config.get("STT_LANGUAGE") == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_config.py -q`
Expected: FAIL — `KeyError`/`AssertionError` (keys not yet in DEFAULT_SETTINGS; `config.get` returns None).

- [ ] **Step 3: Edit `app/config.py`** — add the voice keys to `DEFAULT_SETTINGS`. Replace the existing `DEFAULT_SETTINGS` dict (lines 14-28) with:

```python
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
    # ── 語音（Stage 2） ──
    "STT_PROVIDER": "faster_whisper",               # faster_whisper | fake
    "STT_MODEL": "small",
    "STT_LANGUAGE": "",                             # 空 = 自動偵測
    "TTS_PROVIDER": "edge",                         # edge | fake
    "EDGE_TTS_VOICE": "zh-TW-HsiaoChenNeural",
    "EDGE_TTS_VOICE_EN": "en-US-JennyNeural",
    "VOICE_HISTORY_MAX_TURNS": 4,
    "SESSION_DIR": str(_PROJECT / "data" / "sessions"),
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_config.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/config.py tests/test_config.py
git commit -m "feat(config): add STT/TTS/session settings for voice path"
```

---

## Task 2: AgentContext.lang + Agent history/lang injection

**Files:**
- Modify: `/home/oliver/pos_agent/app/context.py`
- Modify: `/home/oliver/pos_agent/app/agents/base.py`
- Test: `/home/oliver/pos_agent/tests/test_context.py`
- Test: `/home/oliver/pos_agent/tests/test_agent_loop.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_context.py`:

```python
def test_lang_defaults_to_zh():
    assert AgentContext().lang == "zh"
    assert AgentContext(lang="en").lang == "en"
```

And append to `tests/test_agent_loop.py`:

```python
def test_agent_injects_history_into_user_message(menu_file):
    provider = FakeProvider([LLMResponse(text="好的。")])
    ctx = AgentContext(session_id="s1", history=[{"user": "我要可樂", "ai": "已加入可樂。"}])
    agent = Agent(provider, "sys", ["search_menu"], max_iters=3)
    agent.run("改成兩杯", ctx)
    sent_messages = provider.calls[0][0]
    user_msg = [m for m in sent_messages if m.role == "user"][-1]
    assert "對話歷史" in user_msg.content
    assert "我要可樂" in user_msg.content
    assert "改成兩杯" in user_msg.content


def test_agent_no_history_block_when_empty(menu_file):
    provider = FakeProvider([LLMResponse(text="好的。")])
    agent = Agent(provider, "sys", ["search_menu"], max_iters=3)
    agent.run("我要大麥克", AgentContext())
    user_msg = [m for m in provider.calls[0][0] if m.role == "user"][-1]
    assert user_msg.content == "我要大麥克"      # no preamble


def test_agent_adds_english_directive_when_lang_en(menu_file):
    provider = FakeProvider([LLMResponse(text="Sure.")])
    agent = Agent(provider, "你是助理", ["search_menu"], max_iters=3)
    agent.run("I want a Big Mac", AgentContext(lang="en"))
    system_msg = [m for m in provider.calls[0][0] if m.role == "system"][0]
    assert "English" in system_msg.content
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_context.py tests/test_agent_loop.py -q`
Expected: FAIL — `AttributeError: 'AgentContext' object has no attribute 'lang'` and the new agent assertions fail.

- [ ] **Step 3: Edit `app/context.py`** — add the `lang` field. Replace the dataclass body (lines 4-11) with:

```python
@dataclass
class AgentContext:
    session_id: str = "anonymous"
    cart: list = field(default_factory=list)
    history: list = field(default_factory=list)
    mood: int | None = None
    lang: str = "zh"
    cart_actions: list = field(default_factory=list)
    trace: list = field(default_factory=list)
```

(Keep the existing `add_cart_action` / `drain_cart_actions` methods unchanged.)

- [ ] **Step 4: Replace `app/agents/base.py`** with this full content (adds `_format_history` and the injection in `run`):

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


def _format_history(history: list) -> str:
    """把 session 對話歷史組成可注入 user 訊息的文字區塊（provider 無關）。"""
    lines = []
    for turn in history or []:
        u = (turn.get("user") or "").strip()
        a = (turn.get("ai") or "").strip()
        if u:
            lines.append(f"顧客：{u}")
        if a:
            lines.append(f"系統：{a}")
    if not lines:
        return ""
    return "【對話歷史（最近幾輪）】\n" + "\n".join(lines)


class Agent:
    def __init__(self, provider, system_prompt: str, tool_names: list[str], max_iters: int = 6):
        self.provider = provider
        self.system_prompt = system_prompt
        self.tool_names = tool_names
        self.max_iters = max_iters

    def _tools(self):
        return registry.get_tools(self.tool_names)

    def run(self, user_input: str, ctx: AgentContext) -> AgentResult:
        system_prompt = self.system_prompt
        if getattr(ctx, "lang", "zh") == "en":
            system_prompt = system_prompt + "\n\nReply to the customer in English."

        history_block = _format_history(ctx.history)
        user_content = f"{history_block}\n\n{user_input}" if history_block else user_input

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]
        tools = self._tools()
        allowed = {spec.name: spec for spec in tools}
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
                spec = allowed.get(tc.name)
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

- [ ] **Step 5: Run to verify all pass (incl. no regression to existing agent tests)**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_context.py tests/test_agent_loop.py tests/test_agents.py -q`
Expected: PASS (existing 4 agent-loop + 2 agents + new tests, all green).

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/pos_agent
git add app/context.py app/agents/base.py tests/test_context.py tests/test_agent_loop.py
git commit -m "feat(agent): inject session history + english directive via AgentContext"
```

---

## Task 3: Session persistence (domain/session.py)

**Files:**
- Create: `/home/oliver/pos_agent/app/domain/session.py`
- Test: `/home/oliver/pos_agent/tests/test_session.py`

- [ ] **Step 1: Write the failing test `tests/test_session.py`**

```python
from domain import session


def test_append_then_get(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))
    session.append_turn("s1", "我要可樂", "已加入可樂。", [{"action": "add", "item_id": "MCD120"}], "zh")
    hist = session.get_history("s1")
    assert len(hist) == 1
    assert hist[0]["user"] == "我要可樂"
    assert hist[0]["ai"] == "已加入可樂。"
    assert hist[0]["cart_actions"][0]["item_id"] == "MCD120"
    assert hist[0]["lang"] == "zh"
    assert "ts" in hist[0]


def test_get_history_trims_to_max_turns(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))
    monkeypatch.setenv("VOICE_HISTORY_MAX_TURNS", "2")
    for i in range(3):
        session.append_turn("s1", f"u{i}", f"a{i}", [], "zh")
    hist = session.get_history("s1")
    assert [t["user"] for t in hist] == ["u1", "u2"]      # last 2


def test_missing_session_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))
    assert session.get_history("never_seen") == []


def test_session_id_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))
    session.append_turn("../../etc/passwd", "x", "y", [], "zh")
    # file must be written INSIDE tmp_path (no path traversal)
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert "/" not in written[0].name and ".." not in written[0].name
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_session.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.session'`.

- [ ] **Step 3: Write `app/domain/session.py`**

```python
import json
import os
import re
from datetime import datetime

import config


def _safe_id(session_id: str) -> str:
    """只允許英數/底線/連字號，避免路徑穿越。"""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "")
    return cleaned or "anonymous"


def _path(session_id: str) -> str:
    return os.path.join(config.get("SESSION_DIR", "data/sessions"), f"{_safe_id(session_id)}.json")


def _load(session_id: str) -> list:
    try:
        with open(_path(session_id), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_history(session_id: str) -> list:
    max_turns = int(config.get("VOICE_HISTORY_MAX_TURNS", 4))
    return _load(session_id)[-max_turns:]


def append_turn(session_id: str, user: str, ai: str, cart_actions: list, lang: str) -> None:
    turns = _load(session_id)
    turns.append({
        "user": user,
        "ai": ai,
        "cart_actions": cart_actions or [],
        "lang": lang,
        "ts": datetime.now().isoformat(),
    })
    path = _path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(turns, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_session.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/domain/session.py tests/test_session.py
git commit -m "feat: JSON session store (history persistence) in domain layer"
```

---

## Task 4: Voice STT/TTS providers + fakes

**Files:**
- Create: `/home/oliver/pos_agent/app/voice/__init__.py`
- Create: `/home/oliver/pos_agent/app/voice/stt.py`
- Create: `/home/oliver/pos_agent/app/voice/tts.py`
- Create: `/home/oliver/pos_agent/app/voice/fakes.py`
- Test: `/home/oliver/pos_agent/tests/test_voice_providers.py`

- [ ] **Step 1: Write the failing test `tests/test_voice_providers.py`**

```python
import asyncio

from voice.stt import FasterWhisperSTT, get_stt
from voice.tts import EdgeTTSProvider, get_tts
from voice.fakes import FakeSTT, FakeTTS


def test_get_stt_default_and_fake(monkeypatch):
    assert isinstance(get_stt(), FasterWhisperSTT)
    monkeypatch.setenv("STT_PROVIDER", "fake")
    assert isinstance(get_stt(), FakeSTT)


def test_get_tts_default_and_fake(monkeypatch):
    tts = get_tts()
    assert isinstance(tts, EdgeTTSProvider)
    assert tts.audio_format == "mp3"
    monkeypatch.setenv("TTS_PROVIDER", "fake")
    assert isinstance(get_tts(), FakeTTS)


def test_fake_stt_transcribe():
    out = asyncio.run(FakeSTT(text="我要大麥克", language="zh").transcribe("/tmp/x.webm"))
    assert out == {"text": "我要大麥克", "language": "zh"}


def test_fake_tts_synthesize_and_base64():
    assert asyncio.run(FakeTTS().synthesize("hi")) == b"FAKE_AUDIO"
    b64 = asyncio.run(FakeTTS().synthesize_base64("hi"))
    import base64
    assert base64.b64decode(b64) == b"FAKE_AUDIO"


def test_synthesize_base64_empty_text_returns_empty():
    assert asyncio.run(FakeTTS().synthesize_base64("")) == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_voice_providers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'voice.stt'`.

- [ ] **Step 3: Create `app/voice/__init__.py`** (empty file)

```python
```

- [ ] **Step 4: Write `app/voice/stt.py`**

```python
"""STT provider 抽象 + 實作。config STT_PROVIDER 切換（faster_whisper | fake）。"""
import asyncio
import threading
from abc import ABC, abstractmethod

import config


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str) -> dict:
        """音訊檔 → {"text": str, "language": "zh"|"en"}"""


class FasterWhisperSTT(STTProvider):
    _model = None
    _lock = threading.Lock()

    def _init(self):
        if FasterWhisperSTT._model is None:
            from faster_whisper import WhisperModel
            import torch
            model_size = config.get("STT_MODEL", "small")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            print(f"載入 faster-whisper ({model_size}, {compute_type}, {device})...")
            try:
                FasterWhisperSTT._model = WhisperModel(
                    model_size, device=device, compute_type=compute_type, num_workers=2)
            except Exception as e:
                print(f"⚠️ GPU 載入失敗（{e}），退回 CPU int8")
                FasterWhisperSTT._model = WhisperModel(
                    model_size, device="cpu", compute_type="int8", num_workers=2)

    async def transcribe(self, audio_path: str) -> dict:
        self._init()
        language = config.get("STT_LANGUAGE", "") or None

        def _run():
            with FasterWhisperSTT._lock:
                segments, info = FasterWhisperSTT._model.transcribe(
                    audio_path,
                    language=language,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 300},
                )
            text = "".join(seg.text for seg in segments).strip()
            lang = info.language or "zh"
            return {"text": text, "language": "zh" if lang.startswith("zh") else "en"}

        return await asyncio.to_thread(_run)


def get_stt() -> STTProvider:
    provider = config.get("STT_PROVIDER", "faster_whisper")
    if provider == "fake":
        from voice.fakes import FakeSTT
        return FakeSTT()
    return FasterWhisperSTT()
```

- [ ] **Step 5: Write `app/voice/tts.py`**

```python
"""TTS provider 抽象 + 實作。config TTS_PROVIDER 切換（edge | fake）。"""
import asyncio
import base64
import os
import tempfile
from abc import ABC, abstractmethod

import config


class TTSProvider(ABC):
    audio_format: str = "wav"

    @abstractmethod
    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        """文字 → 音訊 bytes"""

    async def synthesize_base64(self, text: str, lang: str = "zh") -> str:
        if not text:
            return ""
        audio = await self.synthesize(text, lang)
        return base64.b64encode(audio).decode("utf-8") if audio else ""


class EdgeTTSProvider(TTSProvider):
    audio_format = "mp3"

    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        import edge_tts
        voice = (
            config.get("EDGE_TTS_VOICE_EN", "en-US-JennyNeural")
            if lang == "en"
            else config.get("EDGE_TTS_VOICE", "zh-TW-HsiaoChenNeural")
        )
        communicate = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp = f.name
        try:
            await communicate.save(tmp)
            with open(tmp, "rb") as fh:
                return fh.read()
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def get_tts() -> TTSProvider:
    provider = config.get("TTS_PROVIDER", "edge")
    if provider == "fake":
        from voice.fakes import FakeTTS
        return FakeTTS()
    return EdgeTTSProvider()
```

- [ ] **Step 6: Write `app/voice/fakes.py`**

```python
"""確定性測試用的 STT/TTS 假實作（不需任何模型/網路）。"""
from voice.stt import STTProvider
from voice.tts import TTSProvider


class FakeSTT(STTProvider):
    def __init__(self, text: str = "我要大麥克", language: str = "zh"):
        self.text = text
        self.language = language

    async def transcribe(self, audio_path: str) -> dict:
        return {"text": self.text, "language": self.language}


class FakeTTS(TTSProvider):
    audio_format = "mp3"

    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        return b"FAKE_AUDIO"
```

- [ ] **Step 7: Run to verify it passes + module imports without the real SDKs needed**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_voice_providers.py -q`
Expected: PASS (5 passed).

Run: `cd /home/oliver/pos_agent && PYTHONPATH=app conda run -n emotion_ui python -c "import voice.stt, voice.tts, voice.fakes; print('import ok')"`
Expected: prints `import ok` (lazy SDK imports mean importing the modules never touches faster_whisper/edge_tts).

- [ ] **Step 8: Commit**

```bash
cd /home/oliver/pos_agent
git add app/voice/__init__.py app/voice/stt.py app/voice/tts.py app/voice/fakes.py tests/test_voice_providers.py
git commit -m "feat(voice): STT/TTS provider abstraction + faster_whisper/edge impls + fakes"
```

---

## Task 5: Voice pipeline (handle_voice)

**Files:**
- Create: `/home/oliver/pos_agent/app/voice/pipeline.py`
- Test: `/home/oliver/pos_agent/tests/test_voice_pipeline.py`

- [ ] **Step 1: Write the failing test `tests/test_voice_pipeline.py`**

```python
import asyncio

import tools.builtin  # noqa: F401
from domain import session
from llm import factory
from llm.fake_provider import FakeProvider
from llm.provider import LLMResponse, ToolCall
from voice import pipeline
from voice.fakes import FakeSTT, FakeTTS


def _agent_script():
    return FakeProvider([
        LLMResponse(text='{"route": "ordering"}'),
        LLMResponse(tool_calls=[ToolCall(id="t1", name="add_to_cart",
                                         arguments={"item_id": "MCD050", "quantity": 1})]),
        LLMResponse(text="已為您加入大麥克。"),
    ])


def test_handle_voice_happy_path(monkeypatch, menu_file, tmp_path):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "get_stt", lambda: FakeSTT(text="我要大麥克", language="zh"))
    monkeypatch.setattr(pipeline, "get_tts", lambda: FakeTTS())
    monkeypatch.setattr(factory, "get_provider_with_fallback", _agent_script)

    out = asyncio.run(pipeline.handle_voice("s1", "/tmp/fake.webm", multi_lang=True))

    assert out["status"] == "success"
    assert out["user_text"] == "我要大麥克"
    assert out["ai_response"] == "已為您加入大麥克。"
    assert out["cart_actions"][0]["item_id"] == "MCD050"
    assert out["audio_format"] == "mp3"
    assert out["audio_base64"]                       # non-empty
    assert out["detected_lang"] == "zh"
    # turn persisted
    assert session.get_history("s1")[-1]["user"] == "我要大麥克"


def test_handle_voice_empty_transcription_errors(monkeypatch, menu_file, tmp_path):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "get_stt", lambda: FakeSTT(text="", language="zh"))
    monkeypatch.setattr(pipeline, "get_tts", lambda: FakeTTS())

    out = asyncio.run(pipeline.handle_voice("s2", "/tmp/fake.webm"))

    assert out["status"] == "error"
    assert out["ai_response"] == ""
    assert session.get_history("s2") == []           # nothing persisted


def test_handle_voice_tts_failure_degrades_to_text(monkeypatch, menu_file, tmp_path):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))

    class BoomTTS(FakeTTS):
        async def synthesize(self, text, lang="zh"):
            raise RuntimeError("tts down")

    monkeypatch.setattr(pipeline, "get_stt", lambda: FakeSTT(text="我要大麥克", language="zh"))
    monkeypatch.setattr(pipeline, "get_tts", lambda: BoomTTS())
    monkeypatch.setattr(factory, "get_provider_with_fallback", _agent_script)

    out = asyncio.run(pipeline.handle_voice("s3", "/tmp/fake.webm"))

    assert out["status"] == "success"
    assert out["ai_response"] == "已為您加入大麥克。"
    assert out["audio_base64"] == ""                 # degraded, but request succeeds
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_voice_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'voice.pipeline'`.

- [ ] **Step 3: Write `app/voice/pipeline.py`**

```python
"""語音 pipeline：STT → orchestrator（agent 核心）→ 持久化 → TTS。非串流。"""
import asyncio

from agents import orchestrator
from context import AgentContext
from domain import session
from voice.stt import get_stt
from voice.tts import get_tts


def _error(message: str, lang: str = "zh") -> dict:
    return {
        "status": "error", "message": message,
        "user_text": "", "ai_response": "", "cart_actions": [], "trace": [],
        "audio_base64": "", "audio_format": "", "detected_lang": lang,
    }


async def handle_voice(session_id: str, audio_path: str, multi_lang: bool = True) -> dict:
    stt = get_stt()
    try:
        r = await stt.transcribe(audio_path)
    except Exception as e:
        return _error(f"STT 失敗: {e}")

    user_text = (r.get("text") or "").strip()
    lang = (r.get("language", "zh") if multi_lang else "zh")
    if not user_text:
        return _error("無法辨識語音內容", lang)

    history = session.get_history(session_id)
    ctx = AgentContext(session_id=session_id, history=history, lang=lang)
    result = await asyncio.to_thread(orchestrator.handle, user_text, ctx)

    try:
        await asyncio.to_thread(
            session.append_turn, session_id, user_text,
            result.ai_response, result.cart_actions, lang,
        )
    except Exception as e:
        print(f"⚠️ session 寫入失敗: {e}")

    tts = get_tts()
    try:
        audio_b64 = await tts.synthesize_base64(result.ai_response, lang)
        audio_format = tts.audio_format
    except Exception as e:
        print(f"⚠️ TTS 失敗: {e}")
        audio_b64, audio_format = "", ""

    return {
        "status": "success",
        "user_text": user_text,
        "ai_response": result.ai_response,
        "cart_actions": result.cart_actions,
        "trace": result.trace,
        "audio_base64": audio_b64,
        "audio_format": audio_format,
        "detected_lang": lang,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_voice_pipeline.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/voice/pipeline.py tests/test_voice_pipeline.py
git commit -m "feat(voice): handle_voice pipeline (STT -> agent -> session -> TTS)"
```

---

## Task 6: Voice route + main wiring

**Files:**
- Create: `/home/oliver/pos_agent/app/api/voice_routes.py`
- Modify: `/home/oliver/pos_agent/app/main.py`
- Test: `/home/oliver/pos_agent/tests/test_voice_api.py`

- [ ] **Step 1: Write the failing test `tests/test_voice_api.py`**

```python
from fastapi.testclient import TestClient

import tools.builtin  # noqa: F401
from llm import factory
from llm.fake_provider import FakeProvider
from llm.provider import LLMResponse
from voice import pipeline
from voice.fakes import FakeSTT, FakeTTS


def _client():
    from main import app
    return TestClient(app)


def test_ask_endpoint_runs_voice_pipeline(monkeypatch, menu_file, tmp_path):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "get_stt", lambda: FakeSTT(text="有什麼推薦", language="zh"))
    monkeypatch.setattr(pipeline, "get_tts", lambda: FakeTTS())
    monkeypatch.setattr(
        factory, "get_provider_with_fallback",
        lambda: FakeProvider([LLMResponse(text='{"route": "general"}'),
                              LLMResponse(text="您好，需要為您點餐嗎？")]),
    )

    resp = _client().post(
        "/api/ask",
        data={"session_id": "s1", "multi_lang": "true"},
        files={"media": ("a.webm", b"FAKEAUDIOBYTES", "audio/webm")},
    )
    body = resp.json()
    assert body["status"] == "success"
    assert body["user_text"] == "有什麼推薦"
    assert body["ai_response"] == "您好，需要為您點餐嗎？"
    assert body["detected_lang"] == "zh"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_voice_api.py -q`
Expected: FAIL — `404` (route not mounted) or import error for `api.voice_routes`.

- [ ] **Step 3: Write `app/api/voice_routes.py`**

```python
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

from voice import pipeline

router = APIRouter()


@router.post("/ask")
async def ask(
    session_id: str = Form(...),
    media: UploadFile = File(...),
    multi_lang: str = Form(default="true"),
):
    suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        temp_path = tmp.name
    try:
        data = await media.read()
        with open(temp_path, "wb") as f:
            f.write(data)
        return await pipeline.handle_voice(
            session_id=session_id,
            audio_path=temp_path,
            multi_lang=multi_lang.lower() == "true",
        )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
```

- [ ] **Step 4: Replace `app/main.py`** with this full content (adds the voice router):

```python
import config
import tools.builtin  # noqa: F401  register all tools at startup
from api import chat_routes, event_routes, menu_routes, voice_routes
from fastapi import FastAPI

app = FastAPI(title="pos_agent")
app.include_router(chat_routes.router, prefix="/api")
app.include_router(menu_routes.router, prefix="/api")
app.include_router(event_routes.router, prefix="/api")
app.include_router(voice_routes.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "provider": config.get("LLM_PROVIDER", "ollama")}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

- [ ] **Step 5: Run to verify it passes + route mounted**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_voice_api.py -q`
Expected: PASS (1 passed).

Run: `cd /home/oliver/pos_agent && PYTHONPATH=app conda run -n emotion_ui python -c "from main import app; print('/api/ask' in [r.path for r in app.routes if hasattr(r,'path')])"`
Expected: prints `True`.

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/pos_agent
git add app/api/voice_routes.py app/main.py tests/test_voice_api.py
git commit -m "feat(api): POST /api/ask voice endpoint + mount voice router"
```

---

## Task 7: Chat route session memory

**Files:**
- Modify: `/home/oliver/pos_agent/app/api/chat_routes.py`
- Test: `/home/oliver/pos_agent/tests/test_api.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_api.py`:

```python
def test_chat_remembers_history_across_turns(monkeypatch, menu_file, tmp_path):
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))

    fake1 = FakeProvider([LLMResponse(text='{"route": "ordering"}'),
                          LLMResponse(text="已為您加入可樂。")])
    monkeypatch.setattr(factory, "get_provider_with_fallback", lambda: fake1)
    _client().post("/api/chat", json={"session_id": "s1", "message": "我要可樂"})

    fake2 = FakeProvider([LLMResponse(text='{"route": "ordering"}'),
                          LLMResponse(text="好的，改成兩杯。")])
    monkeypatch.setattr(factory, "get_provider_with_fallback", lambda: fake2)
    resp = _client().post("/api/chat", json={"session_id": "s1", "message": "改成兩杯"})
    assert resp.json()["ai_response"] == "好的，改成兩杯。"

    # The agent.run call (2nd provider call) must carry the prior turn as history.
    agent_msgs = fake2.calls[1][0]
    user_msg = [m for m in agent_msgs if m.role == "user"][-1]
    assert "我要可樂" in user_msg.content and "對話歷史" in user_msg.content
```

(The existing `test_api.py` already imports `factory`, `FakeProvider`, `LLMResponse`, `ToolCall`, and defines `_client()`. Reuse them; do not redefine.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_api.py::test_chat_remembers_history_across_turns -q`
Expected: FAIL — the 2nd agent call's user message has no history block (chat route doesn't persist/load session yet).

- [ ] **Step 3: Replace `app/api/chat_routes.py`** with this full content:

```python
from fastapi import APIRouter
from pydantic import BaseModel

from agents import orchestrator
from context import AgentContext
from domain import session

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str = "anonymous"
    message: str


@router.post("/chat")
def chat(req: ChatRequest):
    history = session.get_history(req.session_id)
    ctx = AgentContext(session_id=req.session_id, history=history)
    result = orchestrator.handle(req.message, ctx)
    session.append_turn(req.session_id, req.message, result.ai_response, result.cart_actions, "zh")
    return {
        "ai_response": result.ai_response,
        "cart_actions": result.cart_actions,
        "trace": result.trace,
    }
```

- [ ] **Step 4: Run to verify it passes (and the existing chat test still passes)**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest tests/test_api.py -q`
Expected: PASS (existing 5 api tests + 1 new = 6 passed).

> Note: the existing `test_chat_runs_agent` does not set `SESSION_DIR`, so the chat route will read/write under the real default `data/sessions/`. That is acceptable — `get_history` returns `[]` for a fresh `session_id` and the test asserts only the response body. If it proves flaky, the implementer may add `monkeypatch.setenv("SESSION_DIR", str(tmp_path))` to that test, but do not change its assertions.

- [ ] **Step 5: Commit**

```bash
cd /home/oliver/pos_agent
git add app/api/chat_routes.py tests/test_api.py
git commit -m "feat(api): /api/chat shares session memory with voice path"
```

---

## Task 8: Update CLAUDE.md

**Files:**
- Modify: `/home/oliver/pos_agent/CLAUDE.md`

- [ ] **Step 1: Edit `CLAUDE.md`** — make these three changes:

(a) In the **專案概述** section, change the line that begins `第一階段聚焦 agent 核心 + 最小 API（文字 \`/api/chat\` + CLI 驗證）。POS/admin UI、Emotion-LLaMA、WebSocket、完整 RAG、語音 \`/api/ask\` 為後續階段。` to:

```
第一階段：agent 核心 + 最小 API（文字 `/api/chat` + CLI）。第二階段（已完成）：語音路徑 `POST /api/ask`（STT → agent → TTS）+ JSON session 記憶（語音/文字共用）+ zh/en 自動偵測。POS/admin UI、Emotion-LLaMA、WebSocket、完整 RAG 為後續階段。
```

(b) In the **目錄** code block, add these entries (under the existing `app/` tree, before `data/menu.json`):

```
├── voice/           stt + tts（ABC + factory + fakes）+ pipeline(STT→agent→TTS)
├── domain/session.py  JSON session 存（對話歷史，語音/文字共用）
└── api/             chat / menu / event / voice 路由
data/sessions/       runtime session JSON（不提交 git）
```

(c) Replace the **後續階段（尚未實作）** section's first bullet `語音 \`/api/ask\`（STT→orchestrator→TTS）` with:

```
- 語音串流 `/api/ask/stream`（逐句 TTS）、MeloTTS / OpenAI-compatible STT/TTS provider
```

and keep the remaining bullets (POS/admin、WebSocket、Emotion-LLaMA、RAG、心情星星、Gemini 多輪修正) as-is.

- [ ] **Step 2: Final full-suite smoke check**

Run: `cd /home/oliver/pos_agent && conda run -n emotion_ui python -m pytest -q`
Expected: PASS (~71 passed — 51 stage-1 + ~20 new).

Run: `cd /home/oliver/pos_agent && PYTHONPATH=app conda run -n emotion_ui python -c "from main import app; print(sorted(r.path for r in app.routes if hasattr(r,'path')))"`
Expected: includes `/api/ask` alongside the stage-1 routes.

- [ ] **Step 3: Commit**

```bash
cd /home/oliver/pos_agent
git add CLAUDE.md
git commit -m "docs: document stage 2 voice path in CLAUDE.md"
```

---

## Notes for the Implementer

- **Why history is a text block, not replayed Message turns:** prior assistant turns had tool calls we don't want to re-execute or re-serialize per provider. A compact `【對話歷史】` preamble on the current user message is provider-agnostic and matches Project_2026. Injected in `Agent.run`, so every agent (ordering/recommendation/intervention) and both entry points (voice + chat) get it for free.
- **Why fakes + `asyncio.run` instead of pytest-asyncio:** keeps the test toolchain identical to stage 1 (no new plugin) and the providers deterministic with zero models/network. STT/TTS are async, so async unit tests call `asyncio.run(coro)` in plain sync test bodies.
- **Why pipeline monkeypatches `pipeline.get_stt`/`pipeline.get_tts`:** the pipeline binds those names at import (`from voice.stt import get_stt`), so tests patch them on the `pipeline` module. The agent's LLM is intercepted by patching `factory.get_provider_with_fallback` (same pattern as stage-1 `test_api.py`).
- **Graceful degradation:** STT failure / empty transcription → structured error (no persistence, no crash). TTS failure → text response with empty `audio_base64`. Never block the order.
- **Lazy SDK imports:** `faster_whisper`/`torch`/`edge_tts` import inside methods so the app and tests run without them; they're only needed when the real (non-fake) provider actually transcribes/synthesizes.
```
