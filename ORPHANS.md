# Orphan File Audit

This report identifies files and exports that appear unused or disconnected from the current project graph. Nothing was deleted.

## Audit Scope

Checked:

- Frontend module imports under `UI_API/frontend`
- FastAPI route registration and backend imports under `UI_API/backend`
- HTML page reachability through backend routes
- Static image references from HTML, CSS, JavaScript, Python, menu JSON, and Markdown
- Runtime/generated folders such as logs, bytecode, media captures, and vector DB files

Excluded from hard orphan classification:

- `.git/`
- `__pycache__/`
- `.pytest_cache/`
- generated logs
- model checkpoint internals
- Chroma/vector-store internals

## Summary

| Category | Finding |
| --- | --- |
| Definite unused frontend assets | `image3.png`, `image4.png`, `mcd_start.png` |
| Currently unused fallback assets | `UI_API/frontend/menu_images/MCD001.jpg` through `MCD032.jpg` |
| Unreachable pages | None found |
| Frontend modules never imported | None found in current renamed module graph |
| Backend routes not registered | None found |
| Backend services/repositories not reachable from routes/tests | None confirmed |
| Standalone scripts not imported by app runtime | `demo_passive_voice.py`, `import_menu_to_rag.py` |
| Generated/runtime artifacts | present under caches, logs, media, Chroma DB, model folders |

## Definite Orphan Candidates

These files have no active code reference in the current tree.

### Frontend Images

| File | Evidence | Notes |
| --- | --- | --- |
| `UI_API/frontend/image3.png` | Only appears in CSS comments, not in a `url(...)`, HTML tag, JS string, or menu data. | Likely leftover startup-button artwork. |
| `UI_API/frontend/image4.png` | No references found. | Likely old design asset. |
| `UI_API/frontend/mcd_start.png` | No references found. | Likely old startup/landing asset. |

`UI_API/frontend/image2.png` is not orphaned. It is referenced by `UI_API/frontend/shared/styles.css` as the startup overlay background.

## Current Fallback Assets That Are Not Actively Used

These files are not directly referenced by current menu data, but the code can synthesize fallback paths like `/static/menu_images/${id}.jpg` when an item has no `image`.

Current `UI_API/menu_data/menu.json` has `image` populated for every menu item, and none of those values point to `/static/menu_images/...`. Therefore these local files are currently bypassed during normal rendering.

Files:

```text
UI_API/frontend/menu_images/MCD001.jpg
UI_API/frontend/menu_images/MCD002.jpg
UI_API/frontend/menu_images/MCD003.jpg
UI_API/frontend/menu_images/MCD004.jpg
UI_API/frontend/menu_images/MCD005.jpg
UI_API/frontend/menu_images/MCD006.jpg
UI_API/frontend/menu_images/MCD007.jpg
UI_API/frontend/menu_images/MCD008.jpg
UI_API/frontend/menu_images/MCD009.jpg
UI_API/frontend/menu_images/MCD010.jpg
UI_API/frontend/menu_images/MCD011.jpg
UI_API/frontend/menu_images/MCD012.jpg
UI_API/frontend/menu_images/MCD013.jpg
UI_API/frontend/menu_images/MCD014.jpg
UI_API/frontend/menu_images/MCD015.jpg
UI_API/frontend/menu_images/MCD016.jpg
UI_API/frontend/menu_images/MCD017.jpg
UI_API/frontend/menu_images/MCD018.jpg
UI_API/frontend/menu_images/MCD019.jpg
UI_API/frontend/menu_images/MCD020.jpg
UI_API/frontend/menu_images/MCD021.jpg
UI_API/frontend/menu_images/MCD022.jpg
UI_API/frontend/menu_images/MCD023.jpg
UI_API/frontend/menu_images/MCD024.jpg
UI_API/frontend/menu_images/MCD025.jpg
UI_API/frontend/menu_images/MCD026.jpg
UI_API/frontend/menu_images/MCD027.jpg
UI_API/frontend/menu_images/MCD028.jpg
UI_API/frontend/menu_images/MCD029.jpg
UI_API/frontend/menu_images/MCD030.jpg
UI_API/frontend/menu_images/MCD031.jpg
UI_API/frontend/menu_images/MCD032.jpg
```

Recommendation:

- Keep these if offline/fallback menu image support is desired.
- Treat them as removable only if the product intentionally depends on remote menu images.

## Static Assets Confirmed In Use

These are referenced by active code and should not be treated as orphans:

```text
UI_API/frontend/image2.png
UI_API/frontend/mcd_categories/deals.jpg
UI_API/frontend/mcd_categories/drinks.jpg
UI_API/frontend/mcd_categories/kids.jpg
UI_API/frontend/mcd_categories/recommended.jpg
UI_API/frontend/mcd_categories/single.jpg
UI_API/frontend/mcd_categories/value.jpg
```

## Frontend Modules

### Reachable Entry Points

| File | Reachability |
| --- | --- |
| `UI_API/frontend/pos/index.html` | Served by backend routes for `/` and `/pos`; loads `/static/pos/app.js`. |
| `UI_API/frontend/admin/admin.html` | Served by backend `/admin`; loads `/static/admin/admin.js`. |
| `UI_API/frontend/pos/app.js` | POS entry module. |
| `UI_API/frontend/admin/admin.js` | Admin entry module. |

### Imported Modules

All current JavaScript modules under `UI_API/frontend/pos` and `UI_API/frontend/shared` are reachable from `pos/app.js`, `admin/admin.js`, or their imported dependencies:

```text
UI_API/frontend/pos/cart.js
UI_API/frontend/pos/choiceHesitation.js
UI_API/frontend/pos/constants/kiosk.js
UI_API/frontend/pos/media.js
UI_API/frontend/pos/member.js
UI_API/frontend/pos/menuVisuals.js
UI_API/frontend/pos/paymentCountdown.js
UI_API/frontend/pos/runtime.js
UI_API/frontend/pos/state.js
UI_API/frontend/pos/voice.js
UI_API/frontend/shared/apiClient.js
UI_API/frontend/shared/components/VisibilityDisplay.js
UI_API/frontend/shared/hooks/useDomEvents.js
UI_API/frontend/shared/realtimeClient.js
UI_API/frontend/shared/ui.js
```

### Unused Or Questionable Exports

These are not file-level orphans, but they are API surface that appears unused outside its own module:

| Export | File | Evidence |
| --- | --- | --- |
| `getMember()` | `UI_API/frontend/pos/member.js` | Exported but no imports or call sites found. |
| `isMemberFlowVisible()` | `UI_API/frontend/pos/member.js` | Exported but no imports or call sites found. |
| `addDomEventListener()` | `UI_API/frontend/shared/hooks/useDomEvents.js` | Used internally by `useDomReady()`, but no external import found. Consider making it private if no future direct use is intended. |
| `KIOSK_TEXT` | `UI_API/frontend/pos/constants/kiosk.js` | Used internally by helper functions, but no external import found. Consider not exporting it if callers should use `kioskText()` and `kioskFilterLabel()`. |
| `posRuntime` | `UI_API/frontend/pos/runtime.js` | Used internally by runtime helpers, but no external import found. Consider keeping the object private and exporting only accessors. |

## Backend Routes And Services

### Routes

No orphaned FastAPI route modules were found. `UI_API/backend/api/router.py` registers:

```text
core_routes
menu_routes
voice_routes
rag_routes
ai_push_routes
emotion_routes
interaction_routes
realtime_routes
demo_routes
passive_voice_routes
member_routes
test_routes
debug_routes  # conditionally enabled by ENABLE_DEBUG_ROUTES
```

### Services And Repositories

No backend service or repository file was confirmed as orphaned. The apparent low-reference files are still reachable through registered routes, startup hooks, or imported services:

- `backend/services/recommendation_service.py`
- `backend/services/passive_voice_service.py`
- `backend/services/popular_service.py`
- `backend/services/test_service.py`
- `backend/repositories/*`
- `backend/realtime/*`
- `backend/utils/*`

## Standalone Scripts

These files are not imported by the running FastAPI app. They appear to be manual utilities or demos, not accidental orphans:

| File | Purpose |
| --- | --- |
| `UI_API/backend/scripts/demo_passive_voice.py` | Standalone passive voice demo script. |
| `UI_API/backend/scripts/import_menu_to_rag.py` | Standalone menu-to-RAG import utility. |
| `scripts/start_emotion_llama.sh` | Starts the optional Emotion-LLaMA server. |
| `scripts/start_r1_omni.sh` | Starts the optional R1-Omni server and updates emotion provider settings. |

Do not delete these unless the related manual workflow is intentionally removed.

## Runtime And Generated Artifacts

These are not source orphans, but they are generated/runtime files that should usually be excluded from repository commits or cleaned by maintenance scripts.

### Python Bytecode And Caches

Examples:

```text
UI_API/__pycache__/
UI_API/backend/**/__pycache__/
Emotion-LLaMA/**/__pycache__/
R1-Omni/**/__pycache__/
.pytest_cache/
UI_API/.pytest_cache/
```

### Logs

Examples:

```text
logs/r1_omni_server.log
.superpowers/brainstorm/*/state/server.log
```

### Runtime Learning Data And Media

These files are produced or consumed at runtime. They are not orphans in the code sense, but many are session artifacts:

```text
UI_API/learning_data/customer_service_logs.json
UI_API/learning_data/emotion_intervention_logs.json
UI_API/learning_data/interaction_events.json
UI_API/learning_data/intervention_logs.json
UI_API/learning_data/members.json
UI_API/learning_data/rag_docs.json
UI_API/learning_data/rag_review_logs.json
UI_API/learning_data/rag_vector_meta.json
UI_API/learning_data/session_logs.json
UI_API/learning_data/customer_service_media/
UI_API/learning_data/emotion_order_media/
UI_API/learning_data/chroma_rag/
```

### Model Assets

`Emotion-LLaMA/` and `R1-Omni/` are optional model-server trees. They are not imported by the FastAPI app directly, but they are used by the launcher scripts and backend emotion provider settings.

These folders are large:

```text
Emotion-LLaMA/
R1-Omni/
```

Recommendation:

- Keep them if this checkout is meant to run local emotion models.
- Move them outside the main application repository or fetch them during setup if repository size matters.

## Pending Rename/Delete State

The git worktree currently shows old frontend filenames deleted and renamed replacements added. These are not current-file orphans, but they are important during review:

```text
Deleted old paths:
UI_API/frontend/shared/api.js
UI_API/frontend/shared/realtime_client.js
UI_API/frontend/pos/menu_visuals.js
UI_API/frontend/pos/payment_countdown.js
UI_API/frontend/pos/choice_hesitation.js

Current replacements:
UI_API/frontend/shared/apiClient.js
UI_API/frontend/shared/realtimeClient.js
UI_API/frontend/pos/menuVisuals.js
UI_API/frontend/pos/paymentCountdown.js
UI_API/frontend/pos/choiceHesitation.js
```

## Recommended Cleanup Order

1. Confirm whether remote menu images are now the permanent source of truth.
2. If yes, mark `UI_API/frontend/menu_images/MCD001.jpg` through `MCD032.jpg` as removable fallback assets.
3. Confirm that old startup assets are no longer desired.
4. If yes, remove `image3.png`, `image4.png`, and `mcd_start.png` in a separate cleanup commit.
5. Decide whether runtime artifacts under `learning_data/`, logs, caches, and model folders should remain in the repo or move to ignored runtime storage.
6. Make unused exports private only after one runtime smoke test confirms no inline/global usage depends on them.

## Validation Commands Used

```bash
rg -n "from './|from '../|import\\(" UI_API/frontend -g '*.js' -g '*.html'
rg -n "include_router|FileResponse|StaticFiles|mount\\(" UI_API/backend UI_API/main.py UI_API/config.py
rg -n "image2|image3|image4|mcd_start|mcd_categories|menu_images" UI_API/frontend UI_API/menu_data UI_API/backend UI_API/*.md
find UI_API/frontend -type f \( -name '*.js' -o -name '*.html' -o -name '*.css' -o -name '*.png' -o -name '*.jpg' \) -print
```

No deletion commands were run.
