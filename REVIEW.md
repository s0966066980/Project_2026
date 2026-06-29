# Project Code Review

Review date: 2026-06-29

Scope reviewed:
- `UI_API/main.py`, `UI_API/config.py`
- `UI_API/backend/routes`, `services`, `repositories`, `realtime`, `utils`
- `UI_API/frontend/pos`, `frontend/admin`, `frontend/shared`
- Repository hygiene for runtime data, generated files, and model artifacts

I did not modify application code. This file is the only review artifact added.

Validation run:
- `find UI_API -maxdepth 3 -type f -name '*.py' | sort | xargs -r python3 -m py_compile`
  - Result: passed
- `find UI_API/frontend -type f -name '*.js' | sort | xargs -r -n1 node --check`
  - Result: passed
- `python3 -m pytest UI_API/tests -q`
  - Result: not run; current Python environment has no `pytest` module

Existing dirty worktree observed before this review:
- Modified: `.gitignore`, `UI_API/learning_data/settings.json`
- Deleted: `CLAUDE.md`, `README.md`, root image files
- Untracked: `R1-Omni/`, `UI_API/frontend/admin_mockup_preview.html`, `docs/superpowers/specs/2026-06-03-settings-consolidation-design.md`, `scripts/start_r1_omni.sh`

## Findings

### 1. Critical - Admin authentication is disabled in the default mode

File:
- `UI_API/backend/utils/auth_utils.py:6-12`
- `UI_API/backend/routes/core_routes.py:58-105`
- `UI_API/backend/routes/menu_routes.py:17-22`
- `UI_API/backend/routes/rag_routes.py:23-50`
- `UI_API/backend/routes/member_routes.py:169-196`

Explanation:
`require_admin_token()` returns immediately unless `DEMO_PUBLIC_MODE` is enabled. In the default mode, admin APIs for settings, logs, menu mutation, RAG document mutation, and member administration are unauthenticated. This is especially risky because `main.py` also supports ngrok/cloudflared-style tunnel origins and starts on `0.0.0.0` by default.

Suggested fix:
Invert the auth model. Require an admin credential for all admin and destructive endpoints by default, and only allow a deliberate local-dev bypass when bound to loopback or when an explicit `AUTH_DISABLED_FOR_LOCAL_DEV=true` flag is set. Make the dependency fail closed when no admin token is configured.

### 2. Critical - POS/Admin port isolation is broken

File:
- `UI_API/main.py:169-184`
- `UI_API/main.py:299-305`
- `UI_API/backend/routes/core_routes.py:31-41`
- `UI_API/frontend/pos/app.js:28-34`

Explanation:
The same FastAPI app, with all POS and Admin routes included, is served on every available configured port. `/admin` is available on the POS port and `/pos` is available on the Admin port. The frontend also determines mode by path after checking outdated `9000`/`9001` ports, so path alone can switch surfaces. This violates the fixed rule that `8000` must remain POS behavior and `8001` must remain Admin behavior.

Suggested fix:
Create separate POS and Admin ASGI apps or install host/port-aware middleware that rejects `/admin` and admin APIs on the POS port and rejects POS-only pages on the Admin port. Update frontend mode detection to use the actual `8000`/`8001` ports or server-provided boot config.

### 3. High - WebSocket origin and token checks are also disabled by default

File:
- `UI_API/backend/routes/realtime_routes.py:217-237`
- `UI_API/backend/routes/realtime_routes.py:249-260`

Explanation:
`_origin_allowed()` and `_token_allowed()` both return `True` when demo public mode is disabled. That leaves realtime clients connectable without origin validation or token validation in the default mode. Any network-reachable client can connect as `admin`, `pos`, `demo`, or `emotion` if the server is exposed.

Suggested fix:
Apply WebSocket auth independently of demo mode. Require allowed origins and a token for non-loopback connections, and require admin-scoped credentials for `client_type=admin`.

### 4. High - Member login allows account enumeration and session takeover by phone number

File:
- `UI_API/backend/routes/member_routes.py:152-167`
- `UI_API/backend/services/member_service.py:40-58`
- `UI_API/backend/services/member_service.py:185-224`

Explanation:
The code comment already acknowledges the risk: a user can submit any 10-digit phone number, learn whether it exists, bind that member to their session, and read usual orders/history returned by `_public_member()`. Admin list/detail also includes full phone numbers in API payloads once admin auth is bypassed by finding 1.

Suggested fix:
Add OTP or PIN verification before binding a member session. Add per-phone and per-IP rate limits. Return generic login responses that do not reveal whether a phone exists. Keep full phone numbers out of admin list responses unless explicitly needed.

### 5. High - Uploaded media is read fully into memory with no size or content validation

File:
- `UI_API/backend/routes/emotion_routes.py:14-18`
- `UI_API/backend/routes/voice_routes.py:83-110`

Explanation:
Voice and emotion endpoints call `await media.read()` and write the whole upload to disk. There is no size limit, duration limit, MIME validation, or streaming write. A large upload can consume memory and disk, and many concurrent uploads can starve the event loop or fill `/tmp`.

Suggested fix:
Validate `Content-Length` and reject oversized uploads before reading. Stream uploads to temp files in chunks with a hard byte limit. Validate MIME/extension against accepted audio/video formats and cleanly return `413` for too-large payloads.

### 6. High - JSON repositories can lose writes under concurrent requests

File:
- `UI_API/backend/repositories/log_repository.py:35-72`
- `UI_API/backend/repositories/emotion_log_repository.py:111-130`
- `UI_API/backend/repositories/menu_repository.py:156-168`

Explanation:
`log_repository.append_session_log()` performs read-modify-write without a write lock around the whole operation. Two checkouts can read the same list, append separately, and the later `os.replace()` wins, losing one order log. `emotion_log_repository` has a lock but writes directly to the target file instead of using an atomic temp replace. `menu_repository.save_menu()` also writes directly and has no lock.

Suggested fix:
Use per-file locks around read-modify-write sequences and atomic temp-file replacement for every JSON repository. Consider a small SQLite store for append-heavy logs if concurrency increases.

### 7. High - RAG singleton state is mutated concurrently without locks

File:
- `UI_API/backend/services/rag_provider.py:35-53`
- `UI_API/backend/services/rag_provider.py:183-226`
- `UI_API/backend/services/rag_provider.py:259-272`

Explanation:
`RAGProvider` stores model, Chroma client, collection, and BM25 index in class-level globals. `add_document()`, `delete_document()`, `clear_all()`, and `query()` can run in different threads via `asyncio.to_thread()`. `clear_all()` can set `_collection` to `None` while another thread is querying or rebuilding BM25, causing intermittent runtime errors or inconsistent search results.

Suggested fix:
Add a `threading.RLock` around collection and BM25 mutation/read sections. Avoid deleting/recreating the collection while queries run; either serialize all RAG operations or use copy-on-write index rebuilds.

### 8. Medium - Startup lifespan blocks while doing heavy "background" initialization

File:
- `UI_API/main.py:44-47`
- `UI_API/main.py:111-160`

Explanation:
The lifespan handler awaits `_background_init()` before serving traffic. When STT or RAG is enabled, startup can block on local model loading, Chroma initialization, BM25 rebuilds, and optional Gemini setup. The comments call these preload tasks non-blocking, but they block application readiness.

Suggested fix:
Move optional preloads into true background tasks after the app becomes ready, or add strict timeouts and lazy initialization on first use. Keep health/settings endpoints available even if model preloading is slow.

### 9. Medium - Configuration paths depend on the current working directory

File:
- `UI_API/config.py:48-51`

Explanation:
`MENU_JSON_PATH`, `LEARNING_DATA_DIR`, and `SETTINGS_JSON_PATH` are relative paths. The documented command uses `cd UI_API`, but running `python UI_API/main.py` from the repository root creates/reads `./learning_data` and misses `UI_API/menu_data/menu.json`. That can make the menu empty and settings unexpectedly reset in the wrong directory.

Suggested fix:
Resolve paths relative to `Path(__file__).parent` in `config.py`, not the process working directory.

### 10. Medium - Repository read failures are silently converted to empty data

File:
- `UI_API/backend/repositories/log_repository.py:24-29`
- `UI_API/backend/repositories/emotion_log_repository.py:100-108`
- `UI_API/backend/repositories/menu_repository.py:142-153`
- `UI_API/config.py:216-247`

Explanation:
Several repositories catch broad exceptions and return `[]`. A corrupted menu or log file looks identical to "no data", which can hide data loss and cause the POS to fall back to empty/test behavior. `config.load_settings()` can also overwrite invalid settings with defaults after a parse failure.

Suggested fix:
Log structured errors with file paths, return explicit error states for admin-visible data, and preserve corrupt files as `.bad` backups before writing defaults.

### 11. Medium - Checkout returns success even when logging or member finalization fails

File:
- `UI_API/backend/services/checkout_service.py:80-120`
- `UI_API/frontend/pos/app.js:1480-1495`

Explanation:
Checkout logging times out after 5 seconds and returns `{"skipped": true}` while the API still returns `status: "success"`. Member finalization exceptions are swallowed. The frontend also silently ignores checkout write errors and proceeds to completion. This preserves checkout completion, but it makes audit data and member history unreliable without surfacing degradation.

Suggested fix:
Keep checkout non-blocking, but return an explicit `log_status` / `member_status` field and emit a server log or admin event when persistence fails. The frontend can still show completion while telemetry records the failure.

### 12. Medium - Frontend uses unsafe `innerHTML` interpolation for image URLs, emoji fallback, and inline handlers

File:
- `UI_API/frontend/pos/app.js:860-869`
- `UI_API/frontend/pos/app.js:1358-1372`
- `UI_API/frontend/pos/cart.js:84-101`

Explanation:
Most display text is escaped, but `visual.image`, `visual.emoji`, and cart item IDs are interpolated into HTML attributes, inline `onerror`, and inline `onclick` handlers. If menu data is ever admin-edited or compromised, this can become DOM XSS. This risk is amplified by unauthenticated menu updates in finding 1.

Suggested fix:
Build these DOM structures with `createElement`, `setAttribute`, and event listeners instead of HTML strings. Validate menu image URLs server-side against allowed `https://...` or known local static paths.

### 13. Medium - Shared frontend API exports stale endpoint names

File:
- `UI_API/frontend/shared/api.js:121-170`
- `UI_API/backend/routes/rag_routes.py:10-50`
- `UI_API/backend/routes/test_routes.py:64-75`

Explanation:
`shared/api.js` still exports legacy calls such as `/api/rag_docs`, `/api/rag_status`, `/api/ollama_models`, `/api/emotion_clips`, and `/api/emotion_status`. The active backend routes use `/api/rag/docs`, `/api/rag/status`, and `/api/ollama/models`, and there are no active emotion clip/status routes in the current tree. These exports are currently mostly dead code, but future callers will get 404s.

Suggested fix:
Remove unused exports or replace them with the active endpoint paths. Add a small endpoint contract test that imports the frontend API map and checks matching backend routes.

### 14. Medium - RAG status endpoint initializes RAG and always reports enabled

File:
- `UI_API/backend/routes/rag_routes.py:13-20`
- `UI_API/backend/services/rag_provider.py:253-255`

Explanation:
`/api/rag/status` always returns `"enabled": true` and calls `rag.count()`, which initializes the embedding model and Chroma collection even when `RAG_ENABLED` is false. A harmless status check can therefore trigger heavy model setup and report misleading state.

Suggested fix:
Return `config.get("RAG_ENABLED", False)` as the enabled value. If disabled, return `doc_count: 0` or a cheap persisted metadata count without initializing RAG.

### 15. Medium - RAG retrieval lacks a relevance threshold despite the stated insufficient-information rule

File:
- `UI_API/backend/services/rag_provider.py:104-179`

Explanation:
Dense vector results are always fused and returned when documents exist. There is no distance or score threshold, and BM25 zero-hit filtering only applies to the sparse branch. This can inject unrelated context into prompts, conflicting with the rule that insufficient or unrelated retrieval should not let the LLM improvise.

Suggested fix:
Use Chroma distances and BM25 scores to reject low-relevance results. Add a configurable `RAG_SCORE_THRESHOLD` and return `目前文件沒有足夠資訊` behavior when retrieval does not meet it.

### 16. Low - The Ollama startup helper performs side effects before serving the app

File:
- `UI_API/main.py:187-258`
- `UI_API/main.py:283-291`

Explanation:
Starting `main.py` attempts to start `ollama serve` and pull models. Pulling is threaded, but server startup still performs service detection and can spawn local processes. This makes application startup more operationally surprising and harder to control under process managers.

Suggested fix:
Move Ollama bootstrapping to an explicit script or admin health action. Keep `main.py` responsible for serving the API and reporting dependency health.

### 17. Low - `_kill_stray_ngrok()` can terminate unrelated ngrok processes

File:
- `UI_API/main.py:260-280`

Explanation:
The helper uses `pgrep -f ngrok` and sends `SIGTERM` to every matching process except itself. On a shared development machine, this can kill unrelated tunnels owned by the same user or another project.

Suggested fix:
Track the specific pyngrok process this app owns, or remove broad process killing. If cleanup is needed, restrict it to known pyngrok process metadata or ask the operator to clean tunnels manually.

### 18. Low - Local-file frontend mode points to old ports

File:
- `UI_API/frontend/shared/api.js:1-3`
- `UI_API/frontend/shared/realtime_client.js:15-20`
- `UI_API/frontend/pos/app.js:28-34`

Explanation:
When opened from `file:`, the frontend uses `127.0.0.1:9000`, while the current backend ports are `8000` and `8001`. Realtime fallback also uses `127.0.0.1:9000`. This makes local static-file testing fail or hit the wrong service.

Suggested fix:
Update fallback ports to `8000`/`8001`, or remove `file:` mode and require serving through FastAPI.

### 19. Low - Runtime/generated artifacts and large models are present in the workspace

File:
- `UI_API/learning_data/settings.json`
- `Emotion-LLaMA/checkpoints/...`
- `R1-Omni/models/...`
- `**/__pycache__/`
- `**/.pytest_cache/`

Explanation:
The `.gitignore` now ignores most of these, but the working tree still contains runtime settings, Python caches, pytest caches, and very large model files. `UI_API/learning_data/settings.json` is already tracked even though project rules say runtime data should not be committed.

Suggested fix:
Stop tracking runtime settings with `git rm --cached UI_API/learning_data/settings.json` after preserving any needed defaults in code or an example file. Keep model weights outside the repository or in Git LFS/artifact storage, and clean caches from the workspace before packaging or review.

### 20. Low - Dead or preview-only frontend assets are mixed into the app tree

File:
- `UI_API/frontend/admin_mockup_preview.html`
- `UI_API/frontend/image2.png`
- `UI_API/frontend/image3.png`
- `UI_API/frontend/image4.png`

Explanation:
The active admin route serves `frontend/admin/admin.html`, not `admin_mockup_preview.html`. Preview/mockup files and duplicate loose images in `frontend/` make it harder to know which UI is authoritative.

Suggested fix:
Move mockups to a clearly ignored design/prototype folder or delete them if obsolete. Keep only active assets under the served frontend tree.

### 21. Low - Some architecture documentation paths no longer match the active code layout

File:
- `UI_API/backend/...`
- `UI_API/frontend/...`

Explanation:
The project instructions refer to `UI_API/routes`, `UI_API/services`, `UI_API/repositories`, and `UI_API/static`, but this checkout uses `UI_API/backend/...` and `UI_API/frontend/...`. This mismatch increases the chance that future changes target stale paths or miss the active implementation.

Suggested fix:
Update repository instructions and validation commands to match the current layout, or add compatibility notes that the active code is under `backend` and `frontend`.

