# Project Tree and Directory Responsibilities

This document describes the current repository structure, the purpose and responsibility of each directory, notable files, and cleanup opportunities.

Generated folders such as `.git/objects/*`, `__pycache__/`, `.pytest_cache/`, model cache internals, and per-session media folders are summarized rather than expanded file-by-file.

## High-Level Tree

```text
Project_2026/
├── .claude/
├── .gemini/
│   └── skills_build/
├── .git/
├── .pytest_cache/
├── .superpowers/
│   └── brainstorm/
├── .vscode/
├── Emotion-LLaMA/
│   ├── __pycache__/
│   ├── checkpoints/
│   │   ├── Llama-2-7b-chat-hf/
│   │   ├── save_checkpoint/
│   │   └── transformer/
│   ├── eval_configs/
│   └── minigpt4/
│       ├── common/
│       ├── configs/
│       ├── conversation/
│       ├── datasets/
│       ├── models/
│       ├── processors/
│       ├── runners/
│       └── tasks/
├── R1-Omni/
│   ├── __pycache__/
│   ├── humanomni/
│   │   ├── eval/
│   │   └── model/
│   ├── models/
│   │   ├── R1-Omni-0.5B/
│   │   ├── bert-base-uncased/
│   │   ├── siglip-base-patch16-224/
│   │   └── whisper-large-v3/
│   ├── scripts/
│   ├── src/
│   │   ├── distill_r1/
│   │   ├── eval/
│   │   └── r1-v/
│   └── yamls/
├── UI_API/
│   ├── .claude/
│   ├── .git/
│   ├── .pytest_cache/
│   ├── __pycache__/
│   ├── backend/
│   │   ├── api/
│   │   ├── bootstrap/
│   │   ├── core/
│   │   ├── models/
│   │   ├── prompts/
│   │   ├── realtime/
│   │   ├── repositories/
│   │   ├── routes/
│   │   ├── scripts/
│   │   ├── services/
│   │   └── utils/
│   ├── frontend/
│   │   ├── admin/
│   │   ├── mcd_categories/
│   │   ├── menu_images/
│   │   ├── pos/
│   │   │   └── constants/
│   │   └── shared/
│   │       ├── components/
│   │       └── hooks/
│   ├── learning_data/
│   │   ├── chroma_rag/
│   │   ├── customer_service_media/
│   │   └── emotion_order_media/
│   ├── menu_data/
│   └── tests/
├── docs/
│   └── superpowers/
│       ├── plans/
│       └── specs/
├── logs/
└── scripts/
```

## Root Directories

### `.claude/`

- **Purpose:** Local Claude/Codex workspace configuration.
- **Responsibility:** Stores machine-local assistant settings.
- **Major files:** `settings.local.json`.
- **Cleanup note:** Keep out of production packaging. Usually should not be part of application source.

### `.gemini/`

- **Purpose:** Gemini skill/build workspace artifacts.
- **Responsibility:** Stores generated or installed skill-related local tooling.
- **Major files:** `.gemini/skills_build/*`.
- **Cleanup note:** Not required to run the POS application. Candidate for removal from the application repository if not intentionally versioned.

### `.git/`

- **Purpose:** Git repository metadata.
- **Responsibility:** Stores history, refs, hooks, packed objects, and local Git state.
- **Major files:** `config`, `HEAD`, `hooks/`, `refs/`, `objects/`, `sdd/`.
- **Cleanup note:** Required for Git, but never part of deployment artifacts.

### `.pytest_cache/`

- **Purpose:** Pytest runtime cache.
- **Responsibility:** Stores previous test node IDs and last-failed data.
- **Major files:** `CACHEDIR.TAG`, `v/cache/*`.
- **Cleanup note:** Generated cache. Safe to remove and should not be committed.

### `.superpowers/`

- **Purpose:** Local planning/brainstorming workspace artifacts.
- **Responsibility:** Stores planning sessions and state files.
- **Major files:** `brainstorm/*/content`, `brainstorm/*/state`.
- **Cleanup note:** Not required by the application. Candidate for removal or `.gitignore`.

### `.vscode/`

- **Purpose:** Editor configuration.
- **Responsibility:** Stores workspace editor settings.
- **Major files:** `settings.json`.
- **Cleanup note:** Keep only if shared editor settings are intentional.

### `Emotion-LLaMA/`

- **Purpose:** Optional external emotion analysis service.
- **Responsibility:** Provides Emotion-LLaMA model client and MiniGPT4-derived inference code.
- **Major files:** `app_EmotionLlamaClient.py`, `requirements.txt`, `eval_configs/demo.yaml`, license files.
- **Cleanup note:** Large and specialized. If production uses only R1-Omni or no emotion service, this can be split into a separate model-service repository.

### `R1-Omni/`

- **Purpose:** Optional multimodal emotion analysis service.
- **Responsibility:** Provides R1-Omni model server, training/inference scripts, model assets, and YAML configs.
- **Major files:** `r1_omni_server.py`, `inference.py`, `setup.sh`, `yamls/*.yaml`, `humanomni/*.py`.
- **Cleanup note:** Large and specialized. Candidate for a separate model-service repository if the POS app should stay lightweight.

### `UI_API/`

- **Purpose:** Main smart ordering POS application.
- **Responsibility:** Hosts the FastAPI backend, static POS/admin frontend, runtime data, menu data, and tests.
- **Major files:** `main.py`, `config.py`, `requirements.txt`, `requirements-lock.txt`, `backend/`, `frontend/`, `tests/`.
- **Cleanup note:** This is the active application root and should remain.

### `docs/`

- **Purpose:** Project documentation and planning notes.
- **Responsibility:** Stores design specs, implementation plans, and generated planning artifacts.
- **Major files:** `docs/superpowers/specs/*`, `docs/superpowers/plans/*`.
- **Cleanup note:** Keep durable architecture docs. Move transient planning files to an archive if they are not useful to maintainers.

### `logs/`

- **Purpose:** Runtime log output.
- **Responsibility:** Stores logs from local helper scripts and model services.
- **Major files:** `r1_omni_server.log`.
- **Cleanup note:** Generated runtime output. Safe to remove and should not be committed.

### `scripts/`

- **Purpose:** Root-level operational helper scripts.
- **Responsibility:** Starts optional model-backed local workflows.
- **Major files:** `start_emotion_llama.sh`, `start_r1_omni.sh`.
- **Cleanup note:** Keep if local operators use these scripts. Consider parameterizing hardcoded environment paths before sharing.

## Main Application: `UI_API/`

### `UI_API/.claude/`

- **Purpose:** Local assistant settings scoped to `UI_API`.
- **Responsibility:** Stores local tooling configuration.
- **Major files:** `settings.local.json`.
- **Cleanup note:** Not required by the app runtime.

### `UI_API/.git/`

- **Purpose:** Nested Git metadata for `UI_API`.
- **Responsibility:** Indicates `UI_API` may have previously been its own repository or sub-repository.
- **Major files:** `.git/sdd/*`.
- **Cleanup note:** This can confuse root-level Git operations. Candidate for removal if `UI_API` is no longer a nested repo.

### `UI_API/.pytest_cache/`

- **Purpose:** Pytest cache for `UI_API`.
- **Responsibility:** Stores test cache data.
- **Major files:** `CACHEDIR.TAG`, `v/cache/*`.
- **Cleanup note:** Generated. Safe to remove.

### `UI_API/__pycache__/`

- **Purpose:** Python bytecode cache.
- **Responsibility:** Generated by Python imports and compilation.
- **Major files:** `*.pyc`.
- **Cleanup note:** Generated. Safe to remove and should be ignored.

### `UI_API/backend/`

- **Purpose:** Backend source code.
- **Responsibility:** Contains FastAPI composition, routes, services, repositories, realtime infrastructure, prompts, models, utilities, and scripts.
- **Major files:** `ai_services.py`, `app_factory.py`, `database.py`, `__init__.py`.
- **Cleanup note:** Keep. Consider moving legacy compatibility modules only after all imports use package paths.

### `UI_API/frontend/`

- **Purpose:** Static browser frontend.
- **Responsibility:** Provides POS kiosk UI, admin dashboard UI, shared JavaScript/CSS utilities, and image assets.
- **Major files:** `mcd_start.png`, `image2.png`, `image3.png`, `image4.png`, `admin/`, `pos/`, `shared/`.
- **Cleanup note:** Keep. Root-level loose images should be reviewed and either moved into a named asset folder or removed if unused.

### `UI_API/learning_data/`

- **Purpose:** Runtime data store.
- **Responsibility:** Stores settings, logs, member records, RAG documents, vector metadata, uploaded media, and generated analysis artifacts.
- **Major files:** `settings.json`, `members.json`, `session_logs.json`, `interaction_events.json`, `rag_docs.json`.
- **Cleanup note:** Runtime/persistent data. Keep in local/dev, but do not bundle into immutable application images except for seed files.

### `UI_API/menu_data/`

- **Purpose:** Menu source data.
- **Responsibility:** Stores the canonical menu JSON used by the POS and backend services.
- **Major files:** `menu.json`.
- **Cleanup note:** Keep. Consider validating with schema tests.

### `UI_API/tests/`

- **Purpose:** Backend test suite.
- **Responsibility:** Tests member repository/service/routes, checkout member handling, and AI push member behavior.
- **Major files:** `test_member_repository.py`, `test_member_routes.py`, `test_checkout_member.py`, `test_ai_push_member.py`.
- **Cleanup note:** Keep and expand. Remove generated `__pycache__/`.

## Backend Subtree: `UI_API/backend/`

### `UI_API/backend/api/`

- **Purpose:** API composition layer.
- **Responsibility:** Centralizes route dependency construction and router registration.
- **Major files:** `router.py`.
- **Cleanup note:** Keep. This is the correct place for API wiring, not business rules.

### `UI_API/backend/bootstrap/`

- **Purpose:** Application startup and process orchestration.
- **Responsibility:** Handles background model preloading, Ollama startup checks, ngrok cleanup, server banners, and multi-port local Uvicorn startup.
- **Major files:** `startup.py`, `server.py`, `processes.py`.
- **Cleanup note:** Keep. If deployment moves to process managers, production-only startup code can be separated later.

### `UI_API/backend/core/`

- **Purpose:** Backend shared primitives and constants.
- **Responsibility:** Stores app-level constants and infrastructure utilities that are not domain services.
- **Major files:** `constants.py`, `async_utils.py`.
- **Cleanup note:** Keep. Avoid putting feature/business logic here.

### `UI_API/backend/models/`

- **Purpose:** Backend data and dependency models.
- **Responsibility:** Defines structured internal models used across backend layers.
- **Major files:** `dependencies.py`.
- **Cleanup note:** Keep. Expand with request/response/internal models as the API matures.

### `UI_API/backend/prompts/`

- **Purpose:** AI prompt defaults.
- **Responsibility:** Stores reusable system prompts and default prompt strings for AI workflows.
- **Major files:** `defaults.py`.
- **Cleanup note:** Keep. Consider splitting by feature if prompts grow.

### `UI_API/backend/realtime/`

- **Purpose:** WebSocket and realtime event infrastructure.
- **Responsibility:** Manages connected clients and publishes realtime events.
- **Major files:** `connection_manager.py`, `event_bus.py`.
- **Cleanup note:** Keep. Should stay infrastructure-focused.

### `UI_API/backend/repositories/`

- **Purpose:** Persistence/data access layer.
- **Responsibility:** Reads and writes JSON-backed data for logs, menu, members, sessions, interactions, and emotion logs.
- **Major files:** `menu_repository.py`, `member_repository.py`, `log_repository.py`, `interaction_event_repository.py`, `session_repository.py`, `emotion_log_repository.py`.
- **Cleanup note:** Keep. If moving to a database, preserve repository interfaces and replace internals.

### `UI_API/backend/routes/`

- **Purpose:** FastAPI route definitions.
- **Responsibility:** Exposes HTTP/WebSocket endpoints and delegates business behavior to services/repositories.
- **Major files:** `core_routes.py`, `menu_routes.py`, `voice_routes.py`, `ai_push_routes.py`, `emotion_routes.py`, `interaction_routes.py`, `member_routes.py`, `rag_routes.py`, `realtime_routes.py`, `passive_voice_routes.py`, `demo_routes.py`, `debug_routes.py`, `test_routes.py`.
- **Cleanup note:** Keep. Debug/test routes should stay guarded or be excluded from production.

### `UI_API/backend/scripts/`

- **Purpose:** Backend maintenance and demo scripts.
- **Responsibility:** Runs data import or passive voice demo workflows outside the main API process.
- **Major files:** `import_menu_to_rag.py`, `demo_passive_voice.py`.
- **Cleanup note:** Keep if used. Otherwise move demo-only scripts under `tools/` or `examples/`.

### `UI_API/backend/services/`

- **Purpose:** Business logic layer.
- **Responsibility:** Implements AI push, checkout, members, voice, TTS/STT, RAG, emotion analysis, interaction scoring, interventions, scenarios, stats, and tests/diagnostics.
- **Major files:** `ai_push_service.py`, `checkout_service.py`, `member_service.py`, `voice_service.py`, `stt_service.py`, `tts_service.py`, `rag_provider.py`, `emotion_service.py`, `interaction_event_service.py`, `intervention_service.py`, `intervention_pipeline_service.py`, `barrier_state_service.py`, `stats_service.py`, `recommendation_service.py`.
- **Cleanup note:** Keep. Some services may later be grouped by domain if the folder becomes too large.

### `UI_API/backend/utils/`

- **Purpose:** Shared backend utility functions.
- **Responsibility:** Provides authentication, file, and text helpers.
- **Major files:** `auth_utils.py`, `file_utils.py`, `text_utils.py`.
- **Cleanup note:** Keep. Avoid adding domain-specific behavior here.

### `UI_API/backend/**/__pycache__/`

- **Purpose:** Python bytecode caches.
- **Responsibility:** Generated by Python.
- **Major files:** `*.pyc`.
- **Cleanup note:** Remove and ignore.

## Frontend Subtree: `UI_API/frontend/`

### `UI_API/frontend/admin/`

- **Purpose:** Admin dashboard frontend.
- **Responsibility:** Provides operational UI for settings, logs, diagnostics, members, and dashboards.
- **Major files:** `admin.html`, `admin.js`.
- **Cleanup note:** Keep. Consider splitting `admin.js` if it continues to grow.

### `UI_API/frontend/mcd_categories/`

- **Purpose:** Category image assets.
- **Responsibility:** Stores images used by POS category tiles.
- **Major files:** `deals.jpg`, `drinks.jpg`, `kids.jpg`, `recommended.jpg`, `single.jpg`, `value.jpg`.
- **Cleanup note:** Keep if referenced by POS constants. Merge into `frontend/assets/categories/` if asset organization is standardized.

### `UI_API/frontend/menu_images/`

- **Purpose:** Menu item image assets.
- **Responsibility:** Stores local fallback images for menu items.
- **Major files:** `MCD001.jpg` through `MCD032.jpg`.
- **Cleanup note:** Keep if local fallback images are required. If all menu images use official remote URLs, this can be reduced.

### `UI_API/frontend/pos/`

- **Purpose:** POS kiosk frontend.
- **Responsibility:** Implements ordering UI, cart, media capture, voice mode, member flows, hesitation modal, payment countdown, realtime updates, and POS runtime state.
- **Major files:** `index.html`, `app.js`, `cart.js`, `media.js`, `voice.js`, `member.js`, `payment_countdown.js`, `choice_hesitation.js`, `menu_visuals.js`, `runtime.js`, `state.js`.
- **Cleanup note:** Keep. `app.js` is still large and can be split further into controllers once behavior is stabilized.

### `UI_API/frontend/pos/constants/`

- **Purpose:** POS constants and display text.
- **Responsibility:** Stores kiosk category groups and localized UI text.
- **Major files:** `kiosk.js`.
- **Cleanup note:** Keep. If more constants are added, split by domain: `kiosk_text.js`, `categories.js`, `features.js`.

### `UI_API/frontend/shared/`

- **Purpose:** Shared frontend utilities.
- **Responsibility:** Provides API client functions, realtime client, shared UI helpers, CSS, hooks, and simple components.
- **Major files:** `api.js`, `realtime_client.js`, `ui.js`, `styles.css`.
- **Cleanup note:** Keep. As the frontend grows, consider `shared/api/`, `shared/ui/`, and `shared/styles/`.

### `UI_API/frontend/shared/components/`

- **Purpose:** Shared UI component helpers.
- **Responsibility:** Stores small reusable DOM/UI behavior.
- **Major files:** `display.js`.
- **Cleanup note:** Keep if additional components are added. If it remains one tiny file, it could be merged back into `shared/ui.js`.

### `UI_API/frontend/shared/hooks/`

- **Purpose:** Shared browser event hooks.
- **Responsibility:** Stores reusable DOM lifecycle and event helper functions.
- **Major files:** `dom.js`.
- **Cleanup note:** Keep if hook utilities grow. If it remains one tiny file, it could be merged back into `shared/ui.js`.

## Runtime Data Subtree: `UI_API/learning_data/`

### `UI_API/learning_data/chroma_rag/`

- **Purpose:** Chroma vector database storage.
- **Responsibility:** Persists embeddings and vector index files for RAG retrieval.
- **Major files:** `chroma.sqlite3`, UUID-named vector index folders.
- **Cleanup note:** Runtime data. Do not delete unless rebuilding the vector database is acceptable.

### `UI_API/learning_data/customer_service_media/`

- **Purpose:** Customer service media uploads.
- **Responsibility:** Stores recorded customer service clips.
- **Major files:** `*.webm`.
- **Cleanup note:** Runtime media. Candidate for lifecycle cleanup or external object storage.

### `UI_API/learning_data/emotion_order_media/`

- **Purpose:** Emotion analysis media clips.
- **Responsibility:** Stores per-session media clips and `index.json` files for emotion event analysis.
- **Major files:** `pos_*/index.json`, `pos_*/*.webm`.
- **Cleanup note:** Runtime media. Candidate for retention policy or external object storage.

## Model Service Subtrees

### `Emotion-LLaMA/checkpoints/`

- **Purpose:** Emotion-LLaMA model checkpoints.
- **Responsibility:** Stores model weights and transformer checkpoints.
- **Major files:** `minigptv2_checkpoint.pth`, `Llama-2-7b-chat-hf/`, `transformer/chinese-hubert-large/`.
- **Cleanup note:** Very large. Should generally be stored outside Git or managed by download scripts.

### `Emotion-LLaMA/eval_configs/`

- **Purpose:** Emotion-LLaMA runtime configs.
- **Responsibility:** Stores model evaluation/demo configuration.
- **Major files:** `demo.yaml`.
- **Cleanup note:** Keep with the model service.

### `Emotion-LLaMA/minigpt4/`

- **Purpose:** MiniGPT4-derived model code.
- **Responsibility:** Provides common utilities, model definitions, dataset builders, processors, runners, tasks, and conversation handling.
- **Major files:** `__init__.py`, `minigpt4.md`, `common/`, `configs/`, `models/`.
- **Cleanup note:** External model code. Consider vendoring as a submodule or separate dependency.

### `R1-Omni/humanomni/`

- **Purpose:** HumanOmni/R1-Omni model code.
- **Responsibility:** Provides training, inference utilities, model definitions, and conversation helpers.
- **Major files:** `constants.py`, `conversation.py`, `mm_utils.py`, `utils.py`, `train_humanomni.py`, `model/`.
- **Cleanup note:** Keep only if maintaining local model service code in this repo.

### `R1-Omni/models/`

- **Purpose:** R1-Omni model assets.
- **Responsibility:** Stores downloaded Hugging Face model directories and caches.
- **Major files:** `R1-Omni-0.5B/`, `bert-base-uncased/`, `siglip-base-patch16-224/`, `whisper-large-v3/`.
- **Cleanup note:** Very large runtime/model data. Should generally be excluded from Git and restored by setup scripts.

### `R1-Omni/scripts/`

- **Purpose:** R1-Omni training scripts.
- **Responsibility:** Stores fine-tuning shell scripts and DeepSpeed config.
- **Major files:** `finetune_omni.sh`, `finetune_omni_emer.sh`, `finetune_omni_small_sftonMAFWDFEW.sh`, `zero3.json`.
- **Cleanup note:** Keep with R1-Omni service if training is in scope.

### `R1-Omni/src/`

- **Purpose:** R1-Omni research and evaluation source tree.
- **Responsibility:** Stores distillation, evaluation, prompt, and R1-V source code.
- **Major files:** `distill_r1/`, `eval/`, `r1-v/`.
- **Cleanup note:** Candidate for separate model repo if POS application maintainability is the priority.

### `R1-Omni/yamls/`

- **Purpose:** R1-Omni YAML configs.
- **Responsibility:** Stores training/evaluation configuration files.
- **Major files:** `emotion_emer.yaml`, `sft_mafw_dfew.yaml`.
- **Cleanup note:** Keep with R1-Omni service.

## Documentation and Operations

### `docs/superpowers/`

- **Purpose:** Planning and generated specification workspace.
- **Responsibility:** Stores specs and plans produced during development.
- **Major files:** `plans/`, `specs/`.
- **Cleanup note:** Keep final specs; archive stale planning artifacts.

### `docs/superpowers/plans/`

- **Purpose:** Development plans.
- **Responsibility:** Stores implementation planning documents.
- **Major files:** Planning Markdown files.
- **Cleanup note:** Merge useful content into root docs if plans are finalized.

### `docs/superpowers/specs/`

- **Purpose:** Design specifications.
- **Responsibility:** Stores feature and architecture design documents.
- **Major files:** `2026-06-03-settings-consolidation-design.md`.
- **Cleanup note:** Keep durable specs.

### `logs/`

- **Purpose:** Runtime logs.
- **Responsibility:** Stores logs generated by startup scripts and model servers.
- **Major files:** `r1_omni_server.log`.
- **Cleanup note:** Generated. Remove from source control and rotate in production.

### `scripts/`

- **Purpose:** Root helper scripts.
- **Responsibility:** Starts UI_API with optional Emotion-LLaMA or R1-Omni support.
- **Major files:** `start_emotion_llama.sh`, `start_r1_omni.sh`.
- **Cleanup note:** Keep, but replace hardcoded local Python paths with environment variables.

## Merge or Removal Candidates

| Path | Recommendation | Reason |
| --- | --- | --- |
| `.pytest_cache/`, `UI_API/.pytest_cache/` | Remove | Generated test cache; reproducible. |
| `**/__pycache__/` | Remove | Python bytecode cache; reproducible. |
| `logs/` | Remove from Git / keep runtime-only | Runtime output should not be source-controlled. |
| `.superpowers/` | Remove or archive | Local planning state, not required by app runtime. |
| `.gemini/skills_build/` | Remove or move to tooling repo | Local generated skill workspace, not required by app runtime. |
| `UI_API/.git/` | Remove if root repo is canonical | Nested Git metadata can confuse repository operations. |
| `Emotion-LLaMA/checkpoints/` | Move outside repo or fetch on setup | Large model weights and checkpoint data. |
| `R1-Omni/models/` | Move outside repo or fetch on setup | Large downloaded model assets and Hugging Face caches. |
| `UI_API/learning_data/customer_service_media/` | Add retention policy | Runtime media grows indefinitely. |
| `UI_API/learning_data/emotion_order_media/` | Add retention policy | Runtime media grows indefinitely. |
| `UI_API/frontend/shared/components/` + `hooks/` | Keep for growth, or merge into `shared/ui.js` if they stay tiny | Currently small helper folders. |
| `UI_API/frontend/mcd_categories/` + `menu_images/` | Consider merging into `frontend/assets/` | Both are static image asset folders. |
| `Emotion-LLaMA/` and `R1-Omni/` | Consider separate services/repositories | They are optional model services and much larger than the POS app. |
| `UI_API/backend/scripts/` | Keep or move to `tools/` | Demo/import scripts are operational tools, not runtime app code. |

## Recommended Target Structure

If the repository is cleaned for maintainability, a practical target is:

```text
Project_2026/
├── README.md
├── TREE.md
├── UI_API/
│   ├── main.py
│   ├── config.py
│   ├── backend/
│   ├── frontend/
│   ├── menu_data/
│   └── tests/
├── model_services/
│   ├── emotion_llama/              # optional, source only
│   └── r1_omni/                    # optional, source only
├── scripts/
├── docs/
└── runtime/                        # gitignored logs, learning data, model caches
```

This keeps application code, model-service code, docs, scripts, and runtime artifacts clearly separated.
