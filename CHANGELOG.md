# Changelog

All notable architectural refactor changes are documented here.

## 2026-06-29 - Architecture Simplification And Maintainability Pass

### Added

- Added `UI_API/frontend/pos/controllers/kioskMenuController.js`.
  - Owns POS menu loading, category rendering, group navigation, menu filtering, and menu item DOM creation.
  - Keeps kiosk menu behavior reusable and separated from the main POS application coordinator.
  - Preserves existing fallback menu data when `/api/menu` is unavailable.

- Added `UI_API/frontend/shared/httpClient.js`.
  - Centralizes common frontend HTTP helpers:
    - `readJson`
    - `fetchJson`
    - `postFormJson`
    - `postJson`
  - Reduces repeated `fetch(...).json()` patterns in feature services.

- Added `UI_API/backend/utils/parsing.py`.
  - Centralizes safe parsing helpers for route form payloads:
    - `parse_json_list`
    - `parse_non_negative_int`
    - `parse_int_from_decimal`
  - Keeps route handlers focused on request/response flow instead of low-level parsing.

### Changed

- Refactored `UI_API/frontend/pos/app.js`.
  - Removed the inline kiosk menu loading and rendering block from the main app file.
  - Replaced it with a `kioskMenuController` instance.
  - Kept the existing external app-level API:
    - `loadMenu`
    - `renderMenu`
    - `renderKioskCategories`
    - `showMenuGroup`
    - `itemMatchesSubFilter`
  - Reduced the main POS file size from roughly 1955 lines to roughly 1805 lines.
  - Maintained the same menu UI, category switching behavior, item click behavior, and interaction tracking behavior.

- Refactored `UI_API/frontend/shared/apiClient.js`.
  - Replaced repeated JSON/form request boilerplate with shared `httpClient.js` helpers.
  - Kept endpoint-level function names unchanged for existing callers.
  - Preserved special handling for:
    - streaming voice responses
    - raw checkout `Response`
    - cached public settings/menu requests

- Refactored `UI_API/backend/routes/core_routes.py`.
  - Replaced duplicated checkout form parsing with reusable utilities from `utils.parsing`.
  - Preserved existing fallback behavior:
    - JSON arrays are preferred.
    - comma-separated `pushed_ids` and `cart_ids` are still accepted.
    - invalid `cart_sources` still falls back to an empty list.
    - invalid numeric values still fall back to `0`.

- Updated `UI_API/frontend/tsconfig.json`.
  - Added the new `shared/httpClient.js` module to strict `checkJs`.
  - Added the new `pos/controllers/kioskMenuController.js` module to strict `checkJs`.

### Architecture Impact

- Main POS orchestration is simpler.
  - `app.js` now coordinates feature modules instead of owning menu rendering details directly.

- Frontend services are more reusable.
  - HTTP mechanics live in `shared/httpClient.js`.
  - Feature-specific API functions stay in `shared/apiClient.js`.

- Backend route code is more readable.
  - Checkout parsing is now utility-driven and easier to reuse in future routes.

- Coupling is reduced.
  - The menu controller receives dependencies through a factory instead of importing global app state directly.
  - Runtime cross-module dependencies still flow through the existing `runtime.js` dependency registry.

### Unchanged

- No user-facing POS behavior was intentionally changed.
- No API route paths were changed.
- No request or response contracts were intentionally changed.
- No files were deleted.
- No generated runtime data was modified intentionally.

### Validation

Static validation passed:

```bash
find UI_API/frontend -type f -name '*.js' -print | sort | xargs -n 1 node --check
npx --yes -p typescript@6.0.3 tsc -p UI_API/frontend/tsconfig.json
python3 -m py_compile UI_API/backend/routes/core_routes.py UI_API/backend/utils/parsing.py UI_API/backend/app_factory.py UI_API/backend/api/router.py UI_API/main.py
```

Runtime browser/API validation was not performed in this pass.

### Follow-Up Refactor Candidates

- Split `UI_API/frontend/admin/admin.js` into page controllers:
  - stats
  - settings
  - RAG documents
  - emotion logs
  - members
  - test console

- Split more POS workflows out of `UI_API/frontend/pos/app.js`:
  - AI recommendation controller
  - checkout/payment controller
  - interaction tracking controller
  - assist modal controller
  - passive voice controller

- Move large runtime/model assets out of the application repository or fetch them during setup.

- Add browser-level smoke tests for:
  - POS startup
  - menu category switching
  - item add-to-cart
  - checkout
  - admin stats refresh
