# Cleanup Report

Cleanup date: 2026-06-29

Scope:
- Cleanup was based on `REVIEW.md`.
- No runtime behavior fixes were attempted.
- Removals were limited to unused imports, unreferenced shared wrappers, unused media helpers, and an unreferenced preview file.
- Anything that looked runtime-relevant was left unchanged.

## Removed Files

### `UI_API/frontend/admin_mockup_preview.html`

Reason:
- This was a preview/mockup HTML file, not the active Admin entrypoint.
- The active Admin route serves `UI_API/frontend/admin/admin.html`.
- Repo-wide search found no references to `admin_mockup_preview.html`.

Runtime impact:
- None expected. No route or frontend import referenced this file.

## Removed Frontend Functions

### `adminQuerySuffix()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- Active admin code uses direct `fetch()` calls and its own header helper.

Runtime impact:
- None expected.

### `saveSettings()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- The exported wrapper was not called anywhere.
- The active Admin page has its own `saveSettings()` implementation in `UI_API/frontend/admin/admin.js`.

Runtime impact:
- None expected for the active Admin/POS UI.

### `saveMenu()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.

Runtime impact:
- None expected.

### `ask()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- The active voice flow uses `askStream()`.
- Repo-wide search found no `api.ask(...)` callers.

Runtime impact:
- None expected.

### `getLogs()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- Active Admin code fetches logs directly.

Runtime impact:
- None expected.

### `clearLogs()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.

Runtime impact:
- None expected.

### `deleteLog()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.

Runtime impact:
- None expected.

### `clearRagDocs()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- This wrapper pointed to obsolete `/api/rag_docs`.
- Active Admin RAG code calls `/api/rag/docs` directly from `UI_API/frontend/admin/admin.js`.

Runtime impact:
- None expected.

### `uploadRagPdf()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- The wrapper pointed to obsolete `/api/rag_pdf`, which is not an active route in this checkout.

Runtime impact:
- None expected.

### `getEmotionClips()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- The wrapper pointed to an inactive `/api/emotion_clips/{session_id}` path.

Runtime impact:
- None expected.

### `getEmotionStatus()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- The wrapper pointed to an inactive `/api/emotion_status` path.

Runtime impact:
- None expected.

### `clearEmotionClips()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- The wrapper pointed to an inactive `/api/emotion_clips/{session_id}` path.

Runtime impact:
- None expected.

### `getRagDocs()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- The wrapper pointed to obsolete `/api/rag_docs`.

Runtime impact:
- None expected.

### `getRagStatus()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- The wrapper pointed to obsolete `/api/rag_status`.

Runtime impact:
- None expected.

### `getOllamaModels()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- The wrapper pointed to obsolete `/api/ollama_models`; the active backend route is `/api/ollama/models`.

Runtime impact:
- None expected.

### `reviewAllRagDocs()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- The wrapper pointed to obsolete `/api/rag_docs/review_all`.

Runtime impact:
- None expected.

### `addRagDoc()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- This shared wrapper was unused.
- Active Admin RAG code defines and uses its own `addRagDoc()` function in `UI_API/frontend/admin/admin.js`, calling `/api/rag/docs`.

Runtime impact:
- None expected.

### `deleteRagDoc()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- This shared wrapper was unused.
- Active Admin RAG code defines and uses its own `deleteRagDoc()` function in `UI_API/frontend/admin/admin.js`, calling `/api/rag/docs/{doc_id}`.

Runtime impact:
- None expected.

### `getEmotionInterventionLogs()`

File:
- `UI_API/frontend/shared/api.js`

Reason:
- Repo-wide search found no callers.
- Active Admin code fetches `/api/emotion/intervention_logs` directly.

Runtime impact:
- None expected.

### `audioRecorderOptions()`

File:
- `UI_API/frontend/pos/media.js`

Reason:
- Only used by the removed `createAudioRecorder()` helper.
- Repo-wide search found no active callers.

Runtime impact:
- None expected.

### `createAudioRecorder()`

File:
- `UI_API/frontend/pos/media.js`

Reason:
- Repo-wide search found no callers.
- Active voice recording uses `createVideoRecorder()` in `UI_API/frontend/pos/voice.js`.

Runtime impact:
- None expected.

### `captureVideoFrameBlob()`

File:
- `UI_API/frontend/pos/media.js`

Reason:
- Repo-wide search found no callers.
- Active Emotion-LLaMA event capture uses the rolling WebM buffer path.

Runtime impact:
- None expected.

## Removed Imports

### `os`, `asyncio`, `threading`

File:
- `UI_API/backend/ai_services.py`

Reason:
- Static AST scan showed these imports were not referenced in the module.

### `config`

File:
- `UI_API/backend/database.py`

Reason:
- Static AST scan showed this import was not referenced in the module.

### `asyncio`

File:
- `UI_API/backend/routes/rag_routes.py`

Reason:
- Static AST scan showed this import was not referenced in the module.

### `datetime`

File:
- `UI_API/backend/repositories/log_repository.py`

Reason:
- Static AST scan showed this import was not referenced in the module.

### `clean_menu_id`

File:
- `UI_API/backend/services/ai_push_service.py`

Reason:
- Static AST scan and text search showed this imported function was not referenced in the module.

### `createVideoRecorder`, `createAudioRecorder`, `captureVideoFrameBlob`

File:
- `UI_API/frontend/pos/app.js`

Reason:
- Repo-wide text search showed these imported bindings were not used by `app.js`.
- `createVideoRecorder()` itself was kept in `media.js` because `UI_API/frontend/pos/voice.js` still uses it.

## Validation

Commands run:

```bash
find UI_API -maxdepth 3 -type f -name '*.py' | sort | xargs -r python3 -m py_compile
```

Result:
- Passed.

```bash
find UI_API/frontend -type f -name '*.js' | sort | xargs -r -n1 node --check
```

Result:
- Passed.

```bash
python3 -m pytest UI_API/tests -q
```

Result:
- Could not run because the current Python environment does not have `pytest` installed.

## Files Intentionally Left Unchanged

- Runtime/security findings in `REVIEW.md` were not fixed because this request was cleanup-only.
- Referenced assets such as `UI_API/frontend/image2.png` were not removed because CSS still references them.
- Active Admin RAG functions in `UI_API/frontend/admin/admin.js` were not removed because `admin.html` calls them.
- Broad cleanup of generated caches/model files was not performed because it could affect the local development environment and was outside safe runtime-neutral code cleanup.

