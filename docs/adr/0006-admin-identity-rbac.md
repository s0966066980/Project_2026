# ADR-0006：Admin Identity 與 Tenant/Store Scoped RBAC

- 狀態：Accepted
- 日期：2026-07-13
- Owner：Backend / Security / Operations
- Implementation Status：Implemented (Milestone 1C foundation)

## Context

既有 Admin route 使用單一 `ADMIN_API_TOKEN`。共用長期 token 無法辨識個別操作者、限制 tenant/store、撤銷單一 session 或穩定表達 permission，也讓 audit actor 只能推測來源。Project_2026 已具 Tenant → Store → Device hierarchy，因此 Admin authentication 與 authorization 必須以相同 ownership boundary 執行，同時保留受控的舊 token 相容期，避免一次中斷現有部署。

## Decision

- PostgreSQL migration `0003_admin_identity_rbac_foundation.sql` 建立 `admin_users`、`admin_roles`、`admin_permissions`、`admin_role_permissions`、`admin_user_role_assignments` 與 `admin_sessions`。
- Admin user、role、assignment 與 session 使用 application 產生的 UUID。登入 identity 先做 trim、case normalization，並在 tenant 內唯一。
- Password 使用 `argon2-cffi` 的 Argon2id；不保存明文或可逆 password。成功登入時若參數過時，更新 password hash。
- Session credential 使用高 entropy random token；PostgreSQL 只保存 SHA-256 token hash。Session 具 expiry、revoke、last-used 與 atomic rotation lineage。
- Browser session 使用 `HttpOnly`、`SameSite=Strict` cookie；production cookie 另加 `Secure`。Response、log、audit 與 database 不回傳或保存 raw token。
- `AdminPrincipal` 是 route/service 之間的 typed contract：`user_id`、`tenant_id`、`allowed_store_ids`、`roles`、`permissions`、`session_id`、`auth_method`。
- Route 透過集中式 `authorize_admin_request()` / `authorize_admin_action()` 驗證 permission、tenant 與 store；未驗證的 client scope header 或 `X-Admin-User` 不參與 isolation 或 actor 判定。
- Tenant-level role assignment（`store_id IS NULL`）可存取該 tenant 的 active stores；store assignment 只能存取指定 active store。
- Permission 使用穩定 machine name catalog。角色/權限變更、login success/failure、logout、rotation 與 legacy token 使用皆寫入 scoped audit，且不包含 password、token 或完整 login identity。
- `manage_admin_identity.py` 是受信任 provisioning boundary；password 只從 `getpass` 或 `ADMIN_BOOTSTRAP_PASSWORD` environment 取得，不接受 command-line password。

## Compatibility Strategy

- 既有 `require_admin_token()` import 保留，內部先解析正式 Admin session，再處理 legacy token。
- `ENABLE_LEGACY_ADMIN_TOKEN` 在 development/test 預設開啟，在 production 預設關閉；production 若明確開啟，必須同時配置 `ADMIN_API_TOKEN`。
- Legacy principal 僅為 migration window adapter，使用 Default Commercial Scope、每次使用 audit，並標記 `auth_method=legacy_token`。
- 現有 `/admin` 與 `/api/*` 路徑不變；新增的 login/logout/me/rotate 只提供必要 session bootstrap，不進行 Admin UI 大型重構。
- Application rollback 可重新開啟相容 adapter；0003 schema 保留。資料修正或 schema rollback 使用新的 forward migration，不改寫 0003。

## Security Boundary

- Tenant/store scope 來自 database-backed Admin session 與 server configuration，不信任 `X-Tenant-ID`、`X-Store-ID`、`X-Device-ID`。
- Authorization 是 server-side deny-by-default permission check；前端隱藏控制項不能取代 permission enforcement。
- Login failure 使用一致的 safe error，避免暴露帳號存在、disabled 狀態或 password 驗證細節。
- Admin WebSocket 優先以同源 HttpOnly session cookie 驗證；legacy query token 僅在 compatibility flag 開啟時接受，新 Admin frontend 不再把 token 放入 URL。
- Production 必須使用 PostgreSQL。JSON backend 只維持 legacy development/test flow，不保存正式 Admin identity 或 session。

## Consequences

- 可個別撤銷/輪替 session，並以 tenant/store/permission 限制 Admin 行為與 audit actor。
- 部署前需套用 0003、同步 permission catalog、建立首位 Admin user/role，然後關閉 legacy flag。
- Tenant-level assignment 會在 principal 建立時解析 active stores；store 狀態或 role assignment 變更會在下一次 request/session lookup 生效。
- 本 foundation 尚未提供完整 Admin user/role 管理 UI、MFA、OIDC 或跨 tenant super-admin；需要時以後續 milestone 與額外 ADR 演進。

## Alternatives

- 繼續使用共用 Admin token：無法個別撤銷、scope、permission 或可信 audit，拒絕。
- 將 role 字串散落在 route：容易產生不一致與繞過，拒絕，改用 permission machine name 與集中 policy。
- JWT 放在 localStorage：撤銷與 XSS credential exposure 風險較高，拒絕。
- 立即導入 OAuth/OIDC：目前沒有外部 identity provider 與營運需求證據，延後；既有 typed principal 可作未來 adapter contract。
