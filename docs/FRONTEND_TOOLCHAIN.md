# Frontend Toolchain 與相容契約

`UI_API/frontend` 以增量方式導入 Vite、TypeScript、Vitest 與 Playwright。現有 FastAPI 靜態檔案與 DOM contract 保持不變，toolchain build 目前是 deployment-ready artifact 驗證，不會自動取代 production `/static` source。

## Application Boundary

| Application | Production HTML | JavaScript Entry | Server Route |
| --- | --- | --- | --- |
| Kiosk | `kiosk/index.html` | `kiosk/app.js` | `/`, `/kiosk`, `/pos` |
| Admin | `admin/admin.html` | `admin/admin.js` | `/admin` |

Kiosk 不 import Admin state/controller，Admin 不 import Kiosk state/controller。`shared/` 只保存 transport、typed contract、realtime、design token 與純 UI primitive。

## Feature Module Map

- Kiosk：`features/bootstrap` 管 runtime/session preference；既有 `controllers`、`cart.js`、`member.js`、`voice.js`、`media.js`、`paymentCountdown.js` 分別保護 catalog/promotion、cart/member、voice/emotion、checkout concern。
- Admin：`features/auth` 管 login/session gate；`modules/availabilityAdmin.js`、`healthAdmin.js`、`recommendationEventsAdmin.js` 管各自 feature。
- 尚留在 coordinator 的 feature 只按 E2E 保護逐一抽離，不進行同時改版或大爆炸搬移。

## Stable DOM 與 Network Contract

- Kiosk critical DOM：`startSystemBtn`、`menuGrid`、`kioskCartBtn`、`checkoutBtn`、`checkoutOverlay`。
- Admin critical DOM：`adminAuthBackdrop`、`adminAuthForm`、`page-stats`。
- `/static/*`、既有 `/api/*` 與 `/ws/*` 在 feature migration 期間保持相容。
- 新 typed integration 使用 `shared/contracts/api-v1.ts` 與 `shared/api/v1Client.ts`；client 集中 same-origin cookie、Bearer adapter、request ID、timeout、safe GET retry 與 safe error mapping。
- Client 不把 credential 寫入 `localStorage`；legacy Kiosk token/query compatibility 仍待 device-session caller 完成遷移後移除。

## Commands

```bash
cd UI_API/frontend
npm ci --ignore-scripts
npm run typecheck
npm run build
npm run test:coverage
npm run syntax
npx playwright install chromium
npm run test:e2e
```

Playwright 只啟動本機 JSON test server；Kiosk checkout response 與 Admin login response 使用假資料/route interception，不連 production，也不保存 credential/PII。Visual regression 尚無核准 baseline，因此不能宣告 PASS。
