# AGENTS.md

# Project_2026 — 智慧自助點餐與客服介入系統

This file provides instructions for Codex and other AI coding agents working in this repository.

---

## Project Overview

Project_2026 is a prototype system for an **event-triggered multimodal POS customer interaction barrier detection and adaptive service intervention system**.

Core system logic:

1. Observe POS interaction events.
2. Calculate `risk_score`.
3. Trigger short-segment multimodal analysis only when the risk threshold is reached.
4. Generate an executable service intervention action: `intervention_action`.

Important architectural principle:

- Emotion-LLaMA is only one source of multimodal evidence.
- Emotion-LLaMA is **not** the decision core.
- Final decisions must go through the system's risk, evidence, barrier-state, and intervention pipeline.

---

## Tech Stack

- **Backend**: Python 3.x, FastAPI
- **Backend ports**:
  - `8000`: POS client
  - `8001`: Admin console
- **Frontend**: Vanilla JavaScript
  - `app.js`
  - `api.js`
  - `cart.js`
  - `ui.js`
  - `media.js`
- **AI inference**:
  - Ollama
  - `qwen3.5:4b`
  - `nomic-embed-text`
  - Optional Gemini API
- **Speech**:
  - Local Whisper
  - Edge TTS
- **Vision**:
  - YOLO person detection
  - Emotion-LLaMA for emotion and behavior evidence
- **Vector database**:
  - ChromaDB
- **Runtime data**:
  - JSON files for session, logs, menu, and settings
- **Settings**:
  - `.env`
  - `learning_data/settings.json`

---

## Repository Structure

```text
Project_2026/
├── README.md
├── CLAUDE.md
├── AGENTS.md
├── Emotion-LLaMA/
│   └── app_EmotionLlamaClient.py
├── tools/
│   └── pos_interaction_demo_ui.py
└── UI_API/
    ├── main.py
    ├── config.py
    ├── ai_services.py
    ├── rag_service.py
    ├── database.py
    ├── prompts/defaults.py
    ├── routes/
    ├── services/
    ├── repositories/
    ├── realtime/
    ├── utils/
    ├── static/
    ├── menu_data/menu.json
    └── learning_data/
```

Key files:

- `UI_API/main.py`
  - The only main entrypoint.
  - Starts both POS and Admin services.
- `UI_API/config.py`
  - Static settings and dynamic settings manager.
- `UI_API/ai_services.py`
  - Central location for AI service calls.
- `UI_API/rag_service.py`
  - ChromaDB and LangChain RAG logic.
- `UI_API/prompts/defaults.py`
  - Default system prompts.
- `UI_API/routes/`
  - FastAPI endpoints.
- `UI_API/services/`
  - Business logic.
- `UI_API/repositories/`
  - JSON data access.
- `UI_API/realtime/event_bus.py`
  - WebSocket event dispatching.
- `UI_API/menu_data/menu.json`
  - Official menu data.
- `UI_API/learning_data/`
  - Runtime data. Do not commit.

---

## Development Commands

### Start Emotion-LLaMA

```bash
cd Emotion-LLaMA
conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

### Start Ollama

```bash
ollama serve
ollama pull llama3.2
ollama pull nomic-embed-text
```

### Start Main Service

```bash
cd UI_API
conda activate emotion_ui
python main.py
```

Expected services:

```text
POS:   http://127.0.0.1:8000
Admin: http://127.0.0.1:8001
```

---

## Required Validation Commands

When modifying Python files, run relevant syntax checks when possible:

```bash
python3 -m py_compile UI_API/main.py UI_API/config.py UI_API/ai_services.py
python3 -m py_compile UI_API/routes/multimodal_routes.py
python3 -m py_compile UI_API/services/barrier_state_service.py UI_API/services/intervention_service.py
```

When modifying frontend JavaScript files, run relevant syntax checks:

```bash
node --check UI_API/static/app.js
node --check UI_API/static/api.js
node --check UI_API/static/media_buffer.js
```

After backend startup, verify both ports:

```bash
curl http://127.0.0.1:8000/api/settings
curl http://127.0.0.1:8001/api/settings
```

If the required environment is unavailable, clearly state which checks could not be run and why.

---

## Global Coding Rules

Follow these rules for every code modification:

1. Keep diffs minimal.
2. Do not modify unrelated files.
3. Do not perform large refactors unless explicitly requested.
4. Preserve existing public APIs and function signatures unless the requested task requires changing them.
5. Do not change established business flow without explicit instruction.
6. Do not introduce hard-coded absolute paths.
7. Prefer small, incremental patches.
8. Do not change formatting-only or style-only code unless necessary.
9. Do not remove existing behavior unless the user explicitly requests it.
10. When uncertain, explain the risk instead of guessing.

---

## Architecture Rules

### Layer Responsibilities

#### `routes/`

Routes should only:

- Parse requests.
- Validate request payloads.
- Call service-layer functions.
- Return responses.

Routes must not:

- Contain business logic.
- Directly call AI services.
- Directly read or write JSON files.
- Directly manipulate WebSocket connections.

#### `services/`

Services should contain business logic.

Services may:

- Coordinate repositories.
- Coordinate AI service calls through approved service abstractions.
- Implement risk, barrier-state, evidence, and intervention logic.

Services must not:

- Directly read or write JSON files.
- Bypass repositories.
- Directly manipulate low-level WebSocket connections.

#### `repositories/`

Repositories should only handle JSON data access.

Repositories must not:

- Contain business decision logic.
- Call AI services.
- Trigger WebSocket events.
- Decide intervention actions.

#### `ai_services.py`

All AI-related calls should be centralized here, including:

- Whisper
- Ollama
- Gemini
- TTS
- YOLO
- Emotion-LLaMA

Do not scatter AI calls across routes or unrelated services.

---

## Settings Rules

Static settings:

- Ports
- API keys
- Domains
- Environment-specific values

These should be read from `.env` through `config.py`.

Dynamic settings:

- AI parameters
- Feature flags
- Runtime-adjustable admin settings

These should be stored in:

```text
UI_API/learning_data/settings.json
```

Rules:

1. Always read settings using `config.get("KEY")`.
2. Do not directly call `os.getenv` outside the configuration layer.
3. When adding a new setting, define its default value in `DEFAULT_SETTINGS` in `config.py`.
4. Do not break the admin panel's ability to read and write dynamic settings.
5. Do not modify the runtime settings file structure unless repository logic is updated accordingly.

---

## Menu Whitelist Rules

Official menu source:

```text
UI_API/menu_data/menu.json
```

Menu item ID format:

```text
MCDxxx
```

Rules:

1. Voice ordering and AI recommendations must pass through menu whitelist validation.
2. LLM output must not invent menu items.
3. Do not allow hallucinated products to enter the cart.
4. Do not change the `MCDxxx` ID format.
5. Frontend, backend, and RAG logic depend on this ID format.
6. Menu images should reference McDonald's Taiwan online image URLs directly.
7. Do not localize menu images unless explicitly requested.

---

## RAG Rules

RAG should supplement:

- Policies
- Rules
- Customer service scripts
- Combo descriptions
- FAQ-style information

RAG must not:

- Replace the menu whitelist.
- Invent products.
- Override structured menu data.
- Answer from general model knowledge when retrieval is insufficient.

Rules:

1. `manual` type RAG entries are injected as global rules.
2. `manual` entries should not depend on similarity matching.
3. If retrieval score is insufficient, answer with insufficient-information behavior.
4. If the retrieved context is unrelated, do not let the LLM improvise.
5. Preserve source metadata where possible.
6. For multi-document RAG, preserve source identity such as filename, page, or category where available.

Expected insufficient-information behavior:

```text
目前文件沒有足夠資訊
```

---

## WebSocket Rules

Unified WebSocket endpoint:

```text
/ws/{client_type}/{session_id}
```

Allowed `client_type` values:

```text
pos
admin
demo
emotion
```

Rules:

1. Event dispatch must go through `UI_API/realtime/event_bus.py`.
2. Do not directly operate WebSocket connections in routes.
3. Do not directly operate WebSocket connections in business services unless this is already the established abstraction.
4. Avoid duplicate event broadcasting.
5. Avoid introducing event loops or async tasks that can leak after session changes.
6. Ensure POS, Admin, Demo, and Emotion clients receive only the intended events.

---

## Port Isolation Rules

Port behavior is fixed:

```text
8000 = POS client
8001 = Admin console
```

Rules:

1. Port `8000` must always serve POS behavior.
2. Port `8001` must always serve Admin behavior.
3. Do not change port behavior based on path alone.
4. Entering `/admin` on port `8000` must not convert it into Admin behavior.
5. Entering `/pos` on port `8001` must not convert it into POS behavior.
6. Do not modify this logic unless explicitly requested.

---

## Core Business Flow

The canonical business flow is:

```text
POS operation event
→ interaction_event_service calculates risk_score
→ risk_score.triggered = true
→ triggered_multimodal_analysis
→ YOLO + Whisper + Emotion-LLaMA
→ multimodal_evidence_service integrates evidence
→ barrier_state_service infers barrier_state
→ intervention_service decides intervention_action
→ WebSocket pushes updates to POS / Admin / Demo
→ checkout writes back intervention_result
```

Do not bypass this flow.

---

## Barrier State and Intervention Mapping

Current expected mapping:

| barrier_state | common intervention_action |
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

Rules:

1. Emotion labels must not directly determine `intervention_action`.
2. Barrier state must be inferred through `barrier_state_service`.
3. Intervention action must be determined through `intervention_service`.
4. Keep this mapping stable unless explicitly requested.

---

## Emotion Risk Score Rules

Current risk score levels:

| score | level | expected behavior |
|---|---|---|
| 1-2 | `stable` | Save observation only |
| 3-4 | `watch` | Continue observing |
| 5-6 | `assist` | Show assistive message |
| 7-8 | `urgent` | Prioritize calming and notify staff |
| 9-10 | `critical` | Immediately notify staff and stop promotion |

Base scoring logic is located in:

```text
UI_API/services/emotion_risk_service.py
```

Speech content related to complaints, payment failure, or operation difficulty may increase risk weighting.

Rules:

1. Do not let emotion score alone decide final intervention.
2. Do not skip barrier-state inference.
3. Do not skip intervention policy logic.
4. Preserve auditability of risk reasoning where possible.

---

## Forbidden Changes

Do not do the following unless explicitly instructed:

1. Do not modify the `learning_data/` runtime data structure.
2. Do not modify `session_logs`, `intervention_logs`, or `customer_service_logs` schemas unless repository read/write logic is updated together.
3. Do not directly call `ai_services` from routes.
4. Do not directly read or write JSON files from services.
5. Do not allow Emotion-LLaMA emotion labels to directly decide intervention actions.
6. Do not add blocking logic to checkout.
7. Checkout must always be able to complete.
8. Do not commit `.env`.
9. Do not commit model weights.
10. Do not commit `learning_data/` runtime data.
11. Do not commit `chroma_db/`.
12. Do not modify menu item ID format.
13. Do not break POS/Admin port isolation.
14. Do not let LLM-generated menu items bypass whitelist validation.
15. Do not introduce frontend frameworks unless explicitly requested.

---

## Frontend Rules

Frontend is Vanilla JavaScript.

Rules:

1. Do not introduce React, Vue, Svelte, or other frontend frameworks.
2. Keep existing module separation.
3. Avoid global state pollution.
4. Keep cart logic inside cart-related modules.
5. Keep API request logic inside API-related modules.
6. Keep UI rendering logic inside UI-related modules.
7. Do not block the main UI thread with long-running operations.
8. Preserve existing POS interaction flow unless explicitly requested.

Common files:

```text
UI_API/static/app.js
UI_API/static/api.js
UI_API/static/cart.js
UI_API/static/ui.js
UI_API/static/media.js
UI_API/static/media_buffer.js
```

---

## Backend Rules

Backend is Python and FastAPI.

Rules:

1. Preserve FastAPI route/service/repository separation.
2. Keep AI service calls centralized.
3. Avoid blocking async endpoints.
4. Handle exceptions around:
   - file I/O
   - network requests
   - model inference
   - Ollama calls
   - Emotion-LLaMA calls
   - TTS calls
   - Whisper calls
5. Return structured error responses where existing code already follows that pattern.
6. Do not introduce database schema changes unless requested.

---

## Code Review Rules

When asked to review code, review only the relevant diff unless the user asks for a whole-project review.

Prioritize:

1. Correctness
2. Regression risk
3. Business-flow violations
4. Security issues
5. Async/concurrency bugs
6. Broken POS/Admin port isolation
7. Broken menu whitelist behavior
8. Broken checkout behavior
9. RAG hallucination risk
10. Runtime data schema compatibility
11. Error handling
12. Test coverage
13. Maintainability

Do not prioritize:

1. Personal style preference
2. Formatting-only comments
3. Large refactors unrelated to the diff
4. Comments about unchanged code
5. Cosmetic naming issues unless they create real ambiguity

Severity levels:

- `P0`: Must fix before merge. Causes crash, data loss, security issue, blocked checkout, broken startup, or severe business-flow violation.
- `P1`: Should fix before merge. High-probability bug, important regression, broken intervention logic, broken port isolation, or important edge case.
- `P2`: Should fix soon. Maintainability, robustness, test coverage, performance, or moderate architecture issue.
- `P3`: Optional improvement. Low-risk cleanup or minor clarity issue.

Review output format:

```text
[P0/P1/P2/P3] Title

File:
Line or area:

Problem:
Why this matters:
Suggested fix:
```

If no blocking issues are found, say:

```text
No blocking issues found.
```

---

## Code Modification Output Requirements

After modifying code, report:

1. Files changed.
2. Summary of changes.
3. Behavior changes.
4. Validation commands run.
5. Validation results.
6. Manual test steps if automated tests are unavailable.
7. Known risks or limitations.

Do not claim that tests passed unless they were actually run.

---

## Refactoring Rules

Current sprint focus:

```text
Improve code readability.
```

When refactoring:

1. Preserve behavior.
2. Keep public function signatures stable unless explicitly requested.
3. Avoid large cross-cutting rewrites.
4. Prefer extracting small helper functions over redesigning the system.
5. Do not mix refactoring with feature changes unless explicitly requested.
6. Run relevant syntax checks after refactoring.
7. Explain why the refactor improves readability.
8. Mention any files intentionally left unchanged.

---

## Security and Privacy Rules

1. Do not expose `.env` values.
2. Do not log API keys.
3. Do not print secrets in frontend or backend responses.
4. Do not commit runtime data.
5. Do not commit model weights.
6. Avoid sending unnecessary user data to external services.
7. For Gemini or other external APIs, keep calls behind explicit configuration and existing service abstractions.

---

## Git Hygiene Rules

Before making changes:

1. Inspect the current diff when possible.
2. Avoid mixing unrelated changes.
3. Avoid touching generated files.
4. Avoid touching runtime data.

After making changes:

1. Report changed files.
2. Report whether validation commands were run.
3. Report exact validation results.
4. Report if validation could not be run.

Suggested files and directories that should usually be ignored by git:

```gitignore
.env
UI_API/learning_data/
UI_API/chroma_db/
Emotion-LLaMA/**/*.pth
Emotion-LLaMA/**/*.pt
Emotion-LLaMA/**/*.bin
Emotion-LLaMA/**/*.safetensors
```

---

## Related Documents

Consult these documents when relevant:

- `README.md`
  - System overview, startup flow, complete system logic, external deployment notes.
- `CLAUDE.md`
  - Claude-specific project instructions.
- `UI_API/README.md`
  - Detailed UI_API architecture, API list, POS/Admin usage flow.
- `UI_API/PATENT_DESIGN.md`
  - Patent design draft, technical problems, technical means, claim concepts.
- `UI_API/ARCHITECTURE_MAPPING.md`
  - Architecture mapping.

---

## Preferred Codex Workflow

### For code review

```text
Review the current git diff according to AGENTS.md.
Do not modify files.
Only report concrete P0/P1/P2/P3 findings.
Prioritize correctness, regression risk, business-flow violations, async bugs, and security.
```

### For code modification

```text
Read AGENTS.md first.
Make the smallest safe change for the requested task.
Do not modify unrelated files.
Do not perform large refactors.
After editing, report changed files and validation results.
```

### For refactoring

```text
Read AGENTS.md first.
Refactor only the requested area.
Preserve behavior.
Keep the diff minimal.
Do not mix feature changes into the refactor.
Run relevant syntax checks if possible.
```

### For debugging

```text
Read AGENTS.md first.
Analyze the issue before editing.
Identify the likely root cause.
Make the smallest safe fix.
Do not modify unrelated files.
Report changed files, validation results, and remaining risks.
```

---

## Recommended User Prompts for Codex

### Code Review Prompt

```text
請根據 AGENTS.md review 目前 git diff。
不要修改檔案。
請只針對這次修改提出 P0/P1/P2/P3 findings。
優先檢查 correctness、regression、架構規則違反、checkout 是否被阻擋、menu whitelist 是否被繞過、port 8000/8001 是否被破壞。
```

### Code Modification Prompt

```text
請先閱讀 AGENTS.md，然後針對以下需求做最小修改：

需求：
[填入你的需求]

限制：
1. 不要修改 unrelated files
2. 不要大規模重構
3. 不要破壞 routes/services/repositories 分層
4. 不要讓 Emotion-LLaMA 直接決定 intervention_action
5. 不要改 checkout 可完成的邏輯
6. 修改後請回報 changed files、validation commands、known risks
```

### Refactoring Prompt

```text
請先閱讀 AGENTS.md。
我要針對以下區域做 readability refactor：

範圍：
[填入檔案或函式]

限制：
1. 不要改變外部行為
2. 不要改 public function signature
3. 不要混入 feature change
4. 不要修改 unrelated files
5. 修改後請執行相關語法檢查
6. 請說明重構前後差異與風險
```

---

## Final Instruction

When working in this repository, prioritize preserving the system's core business flow and architecture boundaries over making broad improvements.

Correctness, regression safety, and business-rule preservation are more important than style cleanup.
