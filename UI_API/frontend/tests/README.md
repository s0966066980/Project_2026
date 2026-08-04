# Frontend contract tests

Vitest covers the exported API client and kiosk cart module. Playwright covers the supported
browser entry point and live health surface. Tests intentionally exercise public module/browser
interfaces instead of asserting source layout or private implementation details.
