# Performance Audit and Optimization Plan

This document summarizes the current performance profile of the project and the optimizations applied to reduce unnecessary rendering work, duplicate API calls, and avoidable frontend load cost while preserving existing behavior.

## Scope

- Primary surface: `UI_API/frontend/pos`
- Admin surface: `UI_API/frontend/admin`
- Shared frontend services: `UI_API/frontend/shared`
- Backend APIs were reviewed only where frontend request patterns affect load.

## Current Architecture Notes

The frontend is a vanilla JavaScript module application served directly by FastAPI. There is no bundler, framework runtime, or build-time tree shaking. Performance work therefore focuses on:

- Network request coalescing and caching
- DOM batching
- Lazy module/page boundaries
- Avoiding repeated initialization
- Reducing large entrypoint growth
- Keeping polling and media work bounded

## Optimizations Applied

### 1. Shared API Request Coalescing

File: `UI_API/frontend/shared/apiClient.js`

`getMenu()` and `getPublicSettings()` now cache their in-flight promises. This prevents duplicate simultaneous requests from startup, view switching, and feature initialization paths.

Behavior preserved:

- Failed requests clear the cached promise and can be retried.
- Admin-only mutable settings are not cached in the shared client.

Impact:

- Reduces duplicate `/api/menu` and `/api/public_settings` calls.
- Avoids repeated JSON parsing for stable public data.
- Improves startup consistency when multiple modules request the same data.

### 2. POS Menu Load Guard

File: `UI_API/frontend/pos/app.js`

`loadMenu()` now skips network work when `state.menuData` is already populated and shares an in-flight menu request when startup or view switching trigger the same load path.

Impact:

- Prevents redundant menu fetches.
- Prevents unnecessary full menu rerenders after data is already present.
- Keeps fallback menu behavior unchanged.

### 3. Batched Kiosk DOM Rendering

File: `UI_API/frontend/pos/app.js`

Kiosk category cards and menu item rows now render into a `DocumentFragment` and attach to `ui.menuGrid` once.

Impact:

- Reduces repeated DOM insertion work.
- Minimizes layout/reflow pressure during category and menu rendering.
- Keeps the existing row markup, event behavior, and visual output unchanged.

### 4. Admin Menu Cache

File: `UI_API/frontend/admin/admin.js`

The admin menu lookup cache now avoids duplicate fetches and shares an in-flight `/api/menu` request.

Impact:

- Reduces repeated menu metadata loading.
- Keeps fallback behavior for menu name/image lookup unchanged.

### 5. Admin Stats Request Coalescing

File: `UI_API/frontend/admin/admin.js`

`loadStats()` now returns the active request when a refresh is already running.

Impact:

- Prevents overlapping `/api/session_stats` requests from manual refresh and the 15-second polling loop.
- Avoids stale responses competing to rerender the same table.

## Rendering Performance

### Current Hotspots

- `UI_API/frontend/pos/app.js` is a large entrypoint and owns many UI workflows.
- Menu rows are rebuilt when changing groups or filters.
- Cart rendering uses full `innerHTML` replacement for cart rows.
- Admin tables rebuild full table bodies on each stats refresh.
- Some UI text updates query broad selectors during language switching.

### Applied Improvements

- Menu/category render operations now use `DocumentFragment`.
- Menu reloads are guarded to avoid repeated rerender paths.
- Admin stats refreshes are coalesced.

### Recommended Next Steps

- Add keyed DOM updates for cart rows instead of rebuilding the full cart list.
- Memoize filtered menu groups by `groupId`, `filter`, `menuDataVersion`, and `kioskLang`.
- Cache frequently used DOM references currently accessed through repeated `querySelectorAll`.
- Consider virtualizing or paginating admin tables if session records grow large.

## Memoization

### Applied

- Promise memoization for stable API reads:
  - `getMenu()`
  - `getPublicSettings()`
- In-flight guards:
  - POS `loadMenu()`
  - Admin `loadMenu()`
  - Admin `loadStats()`

### Recommended

- Memoize `groupItems(groupId)` and filtered menu item lists.
- Memoize `getMenuVisual(item)` results by item id when menu data is stable.
- Memoize expensive aggregate admin stats if derived repeatedly from the same response.

## Bundle Size

### Current State

There is no bundler. Browser load cost comes from direct ES module graphs and CDN assets.

Large files:

- `UI_API/frontend/pos/app.js`
- `UI_API/frontend/admin/admin.js`
- `UI_API/frontend/shared/styles.css`

External load cost:

- Tailwind CDN runtime script in `UI_API/frontend/pos/index.html`
- Font Awesome CDN stylesheet
- Google Fonts stylesheet

### Recommended

- Replace Tailwind CDN runtime with compiled CSS for production.
- Split `pos/app.js` into route/workflow modules:
  - kiosk menu controller
  - checkout controller
  - AI recommendation controller
  - passive media controller
  - interaction tracking controller
- Split `admin/admin.js` by page:
  - stats
  - settings
  - RAG documents
  - emotion logs
  - members
  - test console
- Add a build step only after module boundaries are stable.

## Lazy Loading

### Current State

POS and admin are already separate HTML pages and module entrypoints:

- `UI_API/frontend/pos/index.html`
- `UI_API/frontend/admin/admin.html`

This avoids loading admin JavaScript on the POS page.

### Recommended

- Lazy-load POS feature modules when first used:
  - member flow
  - voice assistant
  - payment countdown
  - choice hesitation modal
  - passive media capture
- Lazy-load admin page controllers when navigating to the page.
- Defer non-critical CDN assets where possible.

## Duplicate API Calls

### Fixed

- Duplicate stable POS menu/public settings requests are coalesced.
- Duplicate admin menu requests are coalesced.
- Overlapping admin stats refreshes are coalesced.

### Remaining Candidates

- Admin settings-related pages call `/api/settings` from multiple flows.
- RAG settings and RAG docs are loaded together on each RAG tab entry.
- Emotion settings and emotion logs are loaded together on each Emotion tab entry.
- Assist recommendations can be refreshed repeatedly without debounce.

## Unnecessary Rerenders

### Fixed

- POS menu and category DOM insertion is now batched.
- POS menu data reloads no longer force rerender after data is already loaded.
- Admin stats overlapping rerenders are blocked while a request is in flight.

### Remaining Candidates

- Cart rows still fully rebuild for every quantity change.
- Admin tables fully rebuild on every stats refresh.
- Language switching updates broad sections even when the current screen does not need every label.
- AI recommendation cards and assist recommendation lists can be changed to keyed updates.

## Large Components

### Current Large Files

- `UI_API/frontend/pos/app.js`
- `UI_API/frontend/admin/admin.js`

### Recommended Extraction Plan

1. Extract POS menu rendering and filtering into `frontend/pos/menuController.js`.
2. Extract checkout/payment flow into `frontend/pos/checkoutController.js`.
3. Extract interaction tracking into `frontend/pos/interactionTracker.js`.
4. Extract AI push state into `frontend/pos/aiRecommendationController.js`.
5. Extract admin page controllers under `frontend/admin/pages/`.

## Validation

Commands used:

```bash
find UI_API/frontend -type f -name '*.js' -print | sort | xargs -n 1 node --check
npx --yes -p typescript@6.0.3 tsc -p UI_API/frontend/tsconfig.json
```

Notes:

- These checks validate syntax and the strict typed subset configured in `UI_API/frontend/tsconfig.json`.
- They do not replace browser performance profiling or live runtime testing.
- Recommended live checks: Chrome Performance panel, Network panel request count, and Lighthouse production build audit after CDN/build decisions are finalized.

## Future Roadmap

- Add production CSS build to remove Tailwind CDN runtime.
- Add dynamic imports for admin page modules.
- Add keyed cart rendering.
- Add request debounce for manual refresh buttons.
- Add lightweight frontend performance marks around startup, menu render, checkout, and AI recommendation flows.
- Add backend cache headers for stable public assets and menu data if deployment topology allows it.
