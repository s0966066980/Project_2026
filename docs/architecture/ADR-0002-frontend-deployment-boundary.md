# ADR-0002：Kiosk 與 Admin 為獨立前端部署邊界

- 狀態：Accepted
- 日期：2026-07-13

## Context

Kiosk 與 Admin 已分目錄，但目前由同一 FastAPI static mount 交付，build/tooling 仍共用單一 frontend package。兩者在使用者、credential、release cadence、cache、可用性與 UX 風險上不同。

## Decision

- Kiosk Web 與 Admin Web 長期為兩個獨立 application、build artifact 與 deployment。
- Milestone 0 保持現有 `/kiosk`、`/admin` 與 DOM contract。
- Milestone 3 逐步建立 Vite/TypeScript/Vitest/Playwright toolchain。
- 共用內容限於 generated API client、contract、design token、generic realtime/HTTP utility 與 reusable primitive。
- Authentication、business state、page state、DOM state、feature controller 不得跨 application 共用。

## Consequences

- Kiosk 可採穩定、長 cache、裝置導向 release；Admin 可採較快營運功能 release。
- Credential 與 CSP 可依 application 分開設計。
- 需要處理兩份 build/deploy pipeline 與 shared package versioning。

## Rejected Alternatives

- 永久由 FastAPI 直接服務所有前端：部署、cache 與故障邊界不足。
- 第一輪全面 React Rewrite：風險與 diff 過大，且目前 UI/DOM contract 已承載大量行為。
