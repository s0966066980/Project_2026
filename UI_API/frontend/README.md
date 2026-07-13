# UI_API Frontend

`UI_API/frontend/` 包含 Kiosk、Admin、共用 client、樣式與圖片資源。

## 結構

```text
frontend/
├── kiosk/          # 顧客自助點餐
├── admin/          # 營運後台
├── shared/         # 通用 API/realtime client、UI helper、style
├── menu_images/    # 菜單圖片
├── mcd_categories/ # 分類圖片
├── package.json
├── vite.config.ts
├── vitest.config.ts
├── playwright.config.ts
└── tsconfig.json
```

## 邊界

- Kiosk 與 Admin 是不同 application boundary，不互相 import business state、page state、DOM state、authentication state 或 feature controller。
- `shared/` 只放 generic HTTP/API/realtime client、contract、design token、UI primitive 與純 utility。
- 新 API 呼叫優先集中到 client，不持續散落 raw `fetch`。
- 現有 DOM id/class contract 在有明確 migration 與測試前保持穩定。
- 大型畫面依 feature 拆 controller、rendering 與 state；不要只把程式搬到更多無責任邊界的檔案。
- 未驗證資料使用 `textContent` 或明確 escaping，不直接寫入 `innerHTML`。
- 長期 credential 不放 URL 或 `localStorage`。

## 驗證

```bash
cd UI_API/frontend
npm ci --ignore-scripts
npm run typecheck
npm run build
npm run test:coverage
npm run syntax
npm run test:e2e
```

Vite 保持 Kiosk/Admin 獨立 entry；Vitest 測 shared utility/client，Playwright 在本機 JSON test server 驗證 critical DOM/interaction。詳細契約見 [`docs/FRONTEND_TOOLCHAIN.md`](../../docs/FRONTEND_TOOLCHAIN.md)。

## 子模組

- [Kiosk](kiosk/README.md)
- [Admin](admin/README.md)
