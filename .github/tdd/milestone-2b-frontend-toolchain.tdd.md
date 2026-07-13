# Milestone 2B — Frontend Toolchain Foundation TDD Evidence

## Source and DOM Contract

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 2B.

- Production entries remain `kiosk/index.html` + `kiosk/app.js` and `admin/admin.html` + `admin/admin.js`.
- `/kiosk`, `/admin`, `/static/*`, legacy `/api/*` and `/ws/*` paths remain unchanged.
- Critical Kiosk DOM: `startSystemBtn`, `menuGrid`, `checkoutBtn`, `checkoutOverlay`.
- Critical Admin DOM: `adminAuthBackdrop`, `adminAuthForm`, `page-stats`.
- Kiosk and Admin remain independent application entries; shared code contains only transport/contracts/primitives.

## Initial RED

Command: `npm run build; npm test; npm run test:e2e` before dependency installation.

Result: **RED** — `vite: not found`, `vitest: not found`, and the available unrelated `playwright` executable rejected the test command. This proves the previous lockfile/toolchain could not build or execute the new unit/E2E contracts.

## GREEN

Pinned Vite/Vitest/Playwright/TypeScript tooling now builds independent Kiosk/Admin entries. The typed API v1 client centralizes same-origin credentials, correlation, timeout, safe-read retry and safe error mapping without storing credentials in `localStorage`.

- Vite build: **PASS** (24 modules; independent Admin/Kiosk entry artifacts).
- Vitest: **PASS — 3 tests**.
- Typed client coverage: **PASS — 93.33% statements, 82.92% branches, 85.71% functions, 97.36% lines**.
- TypeScript strict check and JavaScript syntax: **PASS**.

## Boundary RED

The first Chromium interaction run reached a populated cart but timed out clicking `checkoutBtn` because the cart panel is intentionally hidden while the menu is active. This captured the existing required journey: open the bottom-bar cart before checkout. The test was corrected without changing product DOM or behavior.

The first explicit Admin login run also classified the expected unauthenticated `/me` 401 as a Chromium console resource error. The harness now discards only that pre-login expected noise after the login backdrop closes, while retaining zero-error assertions for dashboard/logout.

## Browser Verification

Local JSON test server + Chromium: **PASS — 2 tests**.

- Kiosk: start → category/menu → add item → open cart → checkout → completion.
- Admin: unauthenticated login gate → test login → dashboard → logout request.
- No production URL, external API, real credential, payment or PII was used.
- Post-login/critical journey page and console error assertions are clean.

Backend compatibility: **PASS — 263 JSON tests**. API v1/documentation targets: **PASS — 10 tests**. Ruff affected scope, Ruff format, mypy and shell syntax: **PASS**. Python 3.10 remains **NOT RUN locally** because the runtime is unavailable and remains covered by CI.

## Known Limitations

- This milestone establishes the toolchain and typed client foundation; feature-by-feature migration remains Milestone 2C.
- Visual regression has no approved screenshot baseline and must be reported as inconclusive, not PASS.
