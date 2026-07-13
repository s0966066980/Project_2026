# ADR-0007：Per-device Kiosk Identity

- 狀態：Accepted
- 日期：2026-07-13
- Owner：Backend / Security / Operations
- Implementation Status：Implemented (Milestone 1D foundation)

## Context

既有 Kiosk 使用共用 `KIOSK_DEVICE_TOKEN`，無法獨立識別、撤銷或輪替單一裝置，也不能用已驗證 identity 建立 tenant/store/device scope。Milestone 1B 已建立 `devices` ownership；1D 需要在不改變既有 Kiosk UI 與點餐 API contract 的情況下，建立可逐台管理的 credential 與短期 session。

## Decision

- `devices` active record 是已核准的 registration boundary。只有具 `device_identity.manage` permission 且 store scope 相符的 `AdminPrincipal` 能 issue、rotate 或 revoke credential。
- Migration `0004_device_identity_foundation.sql` 新增 `device_credentials`、`device_sessions` 與 `device_credential_events`，並以 composite foreign key 綁定 Tenant → Store → Device ownership。
- Credential 與 session token 都使用 48-byte-class high-entropy random value；PostgreSQL 只保存 SHA-256 hash。`key_id` 是非秘密 lookup identifier。
- Raw credential 只在 issue/rotate response 回傳一次，不寫入 database、event、log、URL 或 frontend storage。
- Credential exchange 產生短期 `DevicePrincipal` session，browser 透過 `HttpOnly`、`SameSite=Strict` cookie 使用；production cookie 加 `Secure`。
- `DevicePrincipal` 包含 `device_id`、`store_id`、`tenant_id`、`credential_id`、`session_id`、issued/expiry 與 auth method。Scope 由 database ownership 解析，忽略 client scope headers。
- Rotation 原子建立 replacement 並設定舊 credential grace deadline。Grace 內允許安全 cutover；deadline 後舊 credential不能建立新 session。Revoke credential 同 transaction 撤銷其 sessions。
- Auth、issue、rotation、revoke 與 legacy token 使用寫入 scoped event，只保存 event type、scope、credential UUID 與 safe metadata。
- 驗證 session 時更新 `last_seen_at`；受限長度的 `X-App-Version` 只作 operational metadata，不參與 authentication 或 scope。

## Compatibility Strategy

- 保留 `require_kiosk_token()` import 與既有 route contract；它先解析正式 device session，再處理 legacy token。
- `ENABLE_LEGACY_KIOSK_TOKEN` 在 development/test 預設開啟，在 production 預設關閉。Production 明確開啟時必須配置 `KIOSK_DEVICE_TOKEN`，且每次使用記錄 deprecated compatibility event。
- Kiosk/checkout/member/recommendation route 暫不改 public request/response。1E 才把 verified `DevicePrincipal` scope 明確傳入所有 service/repository caller。
- Application rollback 可暫時重新啟用 legacy adapter；0004 schema保留，任何修正使用新的 forward migration。

## Security Boundary

- `X-Tenant-ID`、`X-Store-ID`、`X-Device-ID` 與 `X-App-Version` 都不是 isolation credential。
- Credential exchange 有 input length validation、per-key/IP rate limit 與 generic authentication error。
- Kiosk WebSocket 可用同源 HttpOnly device session cookie；legacy URL token 僅在 compatibility flag 開啟時保留，正式 deployment 不使用 URL credential。
- Browser cookie session 降低 raw credential 暴露時間，但不宣稱 TPM、Secure Enclave、hardware attestation 或惡意 browser host 防護。
- Production device identity 只使用 PostgreSQL；JSON backend只維持 development/test legacy flow。

## Consequences

- 單一設備遺失或 credential 洩漏時可獨立 revoke，不影響其他 Kiosk。
- Operations 必須安全保管 issue response、在短時間內完成 credential exchange，並確認 rotation cutover 後撤銷舊 credential。
- Admin UI 尚未提供完整 fleet credential console；現階段提供 server API 與 typed service boundary。
- 完整 heartbeat、rollout ring、remote command 與 diagnostics 屬 Milestone 4C，不在本決策中提前實作。

## Alternatives

- 繼續使用全域 token：無法單機撤銷、scope 或 audit，拒絕。
- 將 raw credential永久保存在 browser `localStorage`：XSS 與複製風險過高，拒絕。
- 只信任 `X-Device-ID`：header 可任意偽造，拒絕。
- 立即要求硬體 attestation：現有 browser kiosk runtime 與營運設備沒有已驗證硬體能力，延後並明確記錄限制。
