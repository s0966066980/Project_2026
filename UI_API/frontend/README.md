# UI_API Frontend

`UI_API/frontend/` 是由 Vite 建置的兩個獨立 browser applications：Kiosk 與 Admin；兩者共用有限的 HTTP/API/realtime/UI primitives。

現有程式以 JavaScript + `// @ts-check` 漸進型別化，typed `/api/v1` client 已建立但 legacy `/api/*` 仍在使用。

## 結構

```text
frontend/
├── kiosk/                    # 顧客點餐 application
├── admin/                    # 營運後台 application
├── shared/
│   ├── apiClient.js          # legacy API facade
│   ├── httpClient.js         # generic HTTP helpers
│   ├── realtimeClient.js     # WebSocket client
│   ├── api/v1Client.ts       # typed /api/v1 client
│   ├── contracts/api-v1.ts   # v1 transport types
│   ├── components/、hooks/   # 共用 primitives
│   └── styles.css、ui.js
├── tests/architecture/       # raw fetch/feature boundary checks
├── tests/unit/               # client/module/allowlist tests
├── tests/e2e/                # Kiosk/Admin critical flows
├── menu_images/、mcd_categories/
├── legacy-api-allowlist.json
├── vite.config.ts
├── vitest.config.ts
├── playwright.config.ts
└── tsconfig.json
```

## 現況與邊界

- Kiosk/Admin 是不同 application boundary，不互相 import business/page/auth/controller state。
- `shared/` 只放雙方真正共用的 transport、contract、hook、UI primitive 與 design token。
- Kiosk 的 API 呼叫大多經 `shared/apiClient.js`；Admin `admin.js` 仍有多處 raw `fetch()`，是已知漸進切換債。
- `shared/api/v1Client.ts` 提供 same-origin credentials、request ID、timeout、GET retry 與 safe error；尚未代表所有頁面已切到 v1。
- Server 是價格、promotion eligibility、member scope、order/payment result 與 permission 的最終真相。
- DOM id/class 是相容 contract；未驗證內容使用 `textContent` 或 escaping。
- Demo/legacy token 只存 `sessionStorage` 並從 URL 移除；長期 credential 不放 URL/`localStorage`。

子模組：

- [Kiosk](kiosk/README.md)
- [Admin](admin/README.md)
- [Shared](shared/README.md)
