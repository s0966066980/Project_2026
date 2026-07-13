# ADR-0002：Kiosk 與 Admin 為獨立前端部署邊界

- 狀態：Accepted
- 日期：2026-07-13
- Owner：Frontend Architecture

## Context

Kiosk 與 Admin 已分目錄，但目前仍由同一 FastAPI application 提供靜態頁面，tooling 與 release 流程尚未完全分離。兩者的使用者、credential、可用性、cache、release cadence 與 UX 風險不同。

## Decision

- Kiosk Web 與 Admin Web 長期為兩個獨立 application、build artifact 與 deployment。
- 遷移期間保留現有 `/kiosk`、`/admin` 與 DOM contract。
- 逐步導入 Vite、TypeScript、Vitest 與 Playwright，不進行一次性全面重寫。
- 共用範圍限於 generated API client、contract、design token、generic HTTP/realtime utility 與 reusable UI primitive。
- Authentication、business state、page state、DOM state 與 feature controller 不跨 application 共用。

## Consequences

正面：

- Kiosk 可採裝置導向、穩定且保守的 release。
- Admin 可獨立發布營運功能。
- Credential、CSP、cache 與故障邊界可分開設計。

代價：

- 需要兩份 build/deploy pipeline。
- Shared package 需要版本與相容治理。
- 遷移期需維持 FastAPI static route 的 backward compatibility。

## Alternatives

- 永久由 FastAPI 直接服務全部前端：部署、cache 與故障邊界不足。
- 第一輪全面 React/Vue Rewrite：Diff 與回歸風險過大，且目前 DOM 已承載大量行為。
