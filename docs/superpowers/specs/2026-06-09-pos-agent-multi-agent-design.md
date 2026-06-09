# pos_agent — 多 Agent 自助點餐核心 設計規格

- **日期**：2026-06-09
- **目標目錄**：`/home/oliver/pos_agent`
- **來源專案**：`/home/oliver/Project_2026`（功能對等、底層改為 multi-agent）
- **狀態**：設計已核准，待寫實作計畫

---

## 1. 目標與範圍

把 Project_2026 從「固定 pipeline + 單次 LLM 強制 JSON 輸出」重構為 **multi-agent + tool-calling** 架構，功能與原專案相仿但 LLM 由被動變主動。

**第一階段交付（本 spec 範圍）**：agent 核心 + 最小 API，用 CLI 與文字 `/api/chat` 驗證 agent 真的會自主呼叫工具。POS/admin UI、Emotion-LLaMA、WebSocket、完整 RAG 留待後續階段，但目錄與抽象需預留接點。

### 不變的原則（沿用原專案）

- 菜單白名單：品項一律來自 `menu.json`（ID 格式 `MCDxxx`），**不允許 LLM 幻覺餐點**。
- checkout 永遠可完成，不加阻擋邏輯。
- 分層職責清楚：route 只解析請求、agent/service 放邏輯、repository 只做資料存取。
- 不提交 `.env`、runtime 資料。

### 核心理念轉變

| 面向 | Project_2026 | pos_agent |
|---|---|---|
| LLM 角色 | 被動：人塞 context → 吐一包 JSON | 主動：持有工具、多步推理、自選工具 |
| 加購物車 | LLM 輸出 `cart_actions` JSON → 事後白名單校正 | LLM 呼叫 `add_to_cart` 工具，**工具內部**強制白名單驗證 |
| 介入決策 | 寫死的 state machine dict | InterventionAgent 推理 + 規則護欄 |
| 模型 | Ollama 為主、Gemini 備援、邏輯寫死 | Provider 抽象層，Claude/Gemini/Ollama 後台可切，雲端失敗自動 fallback 本地 |

---

## 2. 架構：三層抽象

### (a) LLM Provider 層

把三家的 tool-calling 正規化成單一介面：

```python
@dataclass
class Message:
    role: str            # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: list[ToolCall] | None = None   # assistant 發出的工具呼叫
    tool_call_id: str | None = None            # role=="tool" 時對應的呼叫 id

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class LLMResponse:
    text: str                       # 最終文字（無 tool_calls 時為完成）
    tool_calls: list[ToolCall]      # 非空代表需執行工具後再續

class LLMProvider(Protocol):
    name: str
    def run(self, messages: list[Message], tools: list[ToolSpec]) -> LLMResponse: ...
```

- **ClaudeProvider**：Anthropic 原生 tool use；解析 `tool_use` blocks。預設雲端 provider。
- **GeminiProvider**：`google-genai` SDK function calling（沿用原專案 SDK），把 `genai` 的 function call 正規化。
- **OllamaProvider**：用 `/api/chat` 的原生 `tools` 參數（qwen3.5 支援）；對不支援工具的模型 fallback 到手寫 JSON tool loop（沿用原 `_repair_and_extract_json` 概念）。
- **factory.get_provider(name)**：依 `config.get("LLM_PROVIDER")` 選擇；雲端 provider 拋錯（額度/連線）時自動 fallback 到 Ollama，沿用原專案 Gemini cooldown 的概念。

### (b) Tool Registry

工具定義一次，三家共用。各 provider adapter 把 `ToolSpec.parameters`（JSON schema）轉成自家工具格式。

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict                                   # JSON schema
    handler: Callable[[dict, "AgentContext"], "ToolResult"]

@dataclass
class ToolResult:
    content: str                 # 回填給 LLM 的文字（成功摘要或錯誤訊息）
    ok: bool = True
```

工具清單（第一階段）：

| 工具 | 用途 | 白名單/護欄 |
|---|---|---|
| `search_menu(query)` | 依關鍵字/分類查菜單 | 只回 menu.json 內品項 |
| `add_to_cart(item_id, quantity)` | 加入購物車 | **handler 內驗證 item_id ∈ 白名單**，不合法回 error |
| `update_quantity(item_id, quantity)` | 改數量 | 同上 |
| `remove_from_cart(item_id)` | 移除 | 同上 |
| `recommend_items(context, n)` | 推薦 n 品 | 只從白名單選 |
| `query_kb(query)` | RAG 知識查詢（可選，預設關） | 無則回空 |
| `escalate_to_staff(reason)` | 通知真人 | 記 log + 回 ack |

### (c) Agent 基底

跑 tool-calling 迴圈，工具改 `ctx`、不靠 LLM 回傳結構化資料：

```python
class Agent:
    def __init__(self, provider, system_prompt, tool_names, max_iters): ...

    def run(self, user_input: str, ctx: AgentContext) -> AgentResult:
        messages = [Message("system", self.system_prompt), Message("user", user_input)]
        for _ in range(self.max_iters):
            resp = self.provider.run(messages, self._tools())
            messages.append(Message("assistant", resp.text, tool_calls=resp.tool_calls))
            if not resp.tool_calls:
                return AgentResult(ai_response=resp.text, cart_actions=ctx.drain_cart_actions(), trace=ctx.trace)
            for tc in resp.tool_calls:
                result = registry[tc.name].handler(tc.arguments, ctx)
                ctx.trace.append({"tool": tc.name, "args": tc.arguments, "ok": result.ok})
                messages.append(Message("tool", result.content, tool_call_id=tc.id))
        # 達 MAX_ITERS 護欄：回目前累積 + 安全話術
        return AgentResult(ai_response=ctx.fallback_text(), cart_actions=ctx.drain_cart_actions(), trace=ctx.trace)
```

`cart_actions` 由工具 mutate `ctx`，最終 `ai_response` = LLM 完成時的文字。

---

## 3. 四個 Agent 與路由

- **OrchestratorAgent（router 式）**：對話/語音入口。一次輕量分類 → 委派給**一個**子 agent，直接回傳其結果。比 agent-as-tool 巢狀省 token、對弱本地模型更穩、更可控。保留日後升級為 agent-as-tool 的空間。
- **OrderingAgent**：持有 menu/cart 工具，取代 `voice_service` 的單次 JSON 流程。
- **InterventionAgent**：吃 interaction/barrier 事件，推理 + 規則護欄產生介入。**高風險（付款失敗 ≥2 次、疑似抱怨）走確定性規則直接 `escalate_to_staff`，不依賴 LLM**（沿用原 `intervention_service` 的安全邊界）。
- **RecommendationAgent**：AI 推播 / 協助推薦 / 猶豫彈窗，從白名單選品 + 促購短句。

**路由原則**：事件型輸入（barrier_state、interaction_event）**不經 orchestrator LLM**，由事件端點直接呼叫 InterventionAgent，降低延遲。對話/語音才進 orchestrator。

---

## 4. 共享狀態

```python
@dataclass
class AgentContext:
    session_id: str
    cart: list                       # 目前購物車
    history: list                    # 對話歷史
    mood: int | None                 # 心情星星 1-5
    _cart_actions: list              # 本輪工具累積的動作
    trace: list                      # 工具呼叫軌跡（debug / 回傳前端）
```

- 傳進每個 tool handler；工具改 ctx，不靠 LLM 回傳結構。
- Session 用 JSON 持久化（沿用 repository 模式：`domain/session.py`）。

---

## 5. 最小 API（第一階段）

| 端點 | 說明 |
|---|---|
| `POST /api/chat` | 文字輸入 → OrchestratorAgent → `{ai_response, cart_actions, trace}` |
| `GET /api/menu` | 菜單清單 |
| `POST /api/interaction_event` | POS 事件 → 直接打 InterventionAgent |
| `POST /api/barrier_state` | 障礙狀態 → 直接打 InterventionAgent |
| `POST /api/ask`（薄包，預設關） | 音訊 → STT → orchestrator → TTS，沿用原 STT/TTS 抽象 |
| `GET /health` | 健康檢查 |
| `python cli.py` | 互動式 CLI 測試器，無需 UI 即可驗證 agent 自主呼叫工具 |

---

## 6. 目錄結構（target）

```
pos_agent/
├── CLAUDE.md / README.md / .env.example / requirements.txt
├── app/
│   ├── main.py            ← FastAPI entry
│   ├── config.py          ← 靜態(.env) + 動態(settings.json) 設定，沿用原 config.get() 模式
│   ├── context.py         ← AgentContext
│   ├── api/               chat_routes  voice_routes  menu_routes  event_routes
│   ├── agents/            base  orchestrator  ordering  intervention  recommendation
│   ├── llm/               provider  claude_provider  gemini_provider  ollama_provider  factory
│   ├── tools/             registry  menu_tools  cart_tools  recommend_tools  kb_tools  staff_tools
│   ├── domain/            menu(白名單載入/驗證)  session(JSON 存取)
│   └── prompts/           defaults(各 agent system prompt)
├── data/menu.json         ← 從 Project_2026 複製
├── cli.py
└── tests/                 test_tool_loop  test_whitelist  test_providers(FakeProvider)
```

分層職責沿用原專案：`api/` 只解析請求 → 呼叫 agent；agent/tool 放邏輯；`domain/` 只做資料存取與白名單。

---

## 7. 錯誤處理

- **Provider 失敗** → fallback 鏈：雲端（Claude/Gemini）拋錯 → 自動切 Ollama；沿用 cooldown 概念避免反覆打掛掉的雲端。
- **Tool 失敗** → 把錯誤訊息當 `ToolResult(ok=False)` 回給 agent，讓它自我修復或改口，不中斷迴圈。
- **MAX_ITERS 護欄** → 防無限工具迴圈，達上限回安全話術 + 已累積的 cart_actions。
- **白名單拒絕** → `add_to_cart` 等 handler 對非白名單 ID 回 error，agent 道歉而非幻覺餐點。
- **checkout 永不阻擋**（原則延續，雖第一階段無 checkout 端點，設計上預留）。

---

## 8. 測試策略

- **FakeProvider**：回傳腳本化 `tool_calls` 序列，讓 agent loop 在無真實 LLM 下做確定性測試（`test_tool_loop.py`）。
- **白名單測試**（`test_whitelist.py`）：`add_to_cart` 對合法/非法 ID 的行為。
- **Provider 契約測試**（`test_providers.py`）：三家 adapter 對同一 ToolSpec 都能正確序列化工具、解析 tool_calls（可用錄製回應或 FakeProvider 驗證正規化邏輯）。

---

## 9. 已定預設（核准）

1. Orchestrator 採 **router 式**（分類→委派一個 agent），非巢狀 agent-as-tool。
2. 雲端預設 provider = **Claude**，Ollama 為 fallback。
3. 第一階段 voice 為薄包、預設關；先用文字 `/api/chat` + CLI 驗證核心。
4. 技術棧沿用 **Python + FastAPI**。

---

## 10. 後續階段（非本 spec 範圍，僅記接點）

- POS / admin 前端 UI（沿用原 vanilla JS 或重寫）。
- Emotion-LLaMA 事件觸發情緒分析。
- WebSocket 即時介入推送。
- 完整 RAG（fastembed 本地向量）與心情星星 context 注入。
