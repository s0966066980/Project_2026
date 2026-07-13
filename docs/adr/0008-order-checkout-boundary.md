# ADR-0008：Order / Checkout Transaction Boundary

- Status: Accepted
- Implementation Status: Implemented in Milestone 1G
- 日期：2026-07-13
- Owner：Order / Checkout / Operations

## Context

既有 checkout 已由 server 重新計算 menu 與 promotion price，但訂單仍主要寫入 Member 相容資料，缺少正式狀態機、request idempotency、歷史價格 snapshot、atomic outcome 與可靠事件發布邊界。重複點擊、connection reset 或 side-effect failure 可能造成重複或部分寫入。

## Decision

- `orders` 是正式 Order aggregate；`member_orders` 暫時保留為舊會員報表相容 read model。
- 狀態只可依 domain policy 轉移：`draft → pricing → pending_confirmation → confirmed → payment_pending → paid → preparing → completed`，另有 `cancel_pending → cancelled` 與明確 `failed` terminal path。Route 不接受任意狀態字串。
- Client 只提交 item、quantity、options 與 promotion reference；base、option、discount、tax、currency 與 total 均由 server catalog/promotion policy計算。
- Order 保存 product name、category、base/option/discount/final price、promotion、currency 與 calculation version snapshot，後續 catalog 變更不得改寫歷史訂單。
- `Idempotency-Key` uniqueness 位於 tenant＋store scope。同 key＋同 fingerprint 回傳原結果；同 key＋不同 fingerprint 回傳 conflict。
- Order、items、promotion usage、initial outcome 與 `order_confirmed` outbox 在同一 PostgreSQL transaction commit。Terminal transition 同 transaction 建立 completed/cancelled outbox。
- AI、recommendation、emotion 與 analytics 是非關鍵 side effect；其 timeout 或失敗不得回滾已確認的 Order。

## Consequences

- Retry、duplicate click 與 concurrent request 可安全收斂至單一 Order。
- Transactional outbox 保存可靠發布意圖，但正式 consumer、retry scheduling 與 dead-letter operations 延至 Milestone 2E Worker。
- Payment provider 尚未整合；`payment_pending` 與 `paid` 只定義狀態 contract，不宣稱已處理金流。
- Legacy JSON checkout 仍維持相容流程，不是多 instance idempotency 或商業交易一致性邊界。

## Alternatives

- 使用 session ID 當永久 Order ID：拒絕；session lifecycle 與商業訂單 identity 不同。
- 信任 client total 再於後台 reconciliation：拒絕；會把價格竄改帶入交易 source。
- 先寫 Order 再分別寫 items/outbox：拒絕；connection reset 可產生 partial write。
- Checkout 同步等待 AI/推薦：拒絕；非關鍵 provider 不應影響基本交易可用性。

## Compatibility and Recovery

既有 `/api/checkout` Form contract 保留，response 只增補 `order`。未提供 header 的 legacy caller 以 session-scoped compatibility key 執行。0007 是 forward-only migration；問題以 application rollback 或新 migration roll-forward 處理，不改寫 checksum。部署前需備份並驗證 0001–0006 clean；部署後執行 concurrent idempotency、rollback、scope isolation 與 outbox integration。
