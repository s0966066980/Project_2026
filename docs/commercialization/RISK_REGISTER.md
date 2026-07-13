# 商業化 Risk Register

評分：Impact 與 Likelihood 使用 1（低）至 5（高）。Priority 依目前商業化阻斷程度排序，不代表已接受風險。

| ID | Risk | Impact | Likelihood | Priority | Accountable role | Current control | Required mitigation | Target milestone | Status |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| R-001 | 會員以 phone-only 登入，可列舉或冒用 | 5 | 4 | P0 | Identity / Security | Kiosk token、IP/phone rate limit、audit | OTP/PIN、failure policy、device scope、anti-enumeration | M2 | Open |
| R-002 | 無 tenant/store/device scope，資料可能跨商業邊界混用 | 5 | 4 | P0 | Architecture / Data | 無正式 commercial scope | Tenant/Store/Device model、scoped repository、authorization tests | M2 | Open |
| R-003 | Admin 僅 long-lived token，無 user/RBAC/session | 5 | 4 | P0 | Security / Admin | Server token auth、audit | User/Role/Permission、HttpOnly session、store scope、rotation | M2 | Open |
| R-004 | WebSocket、voice session、emotion cache 為 process-local | 4 | 5 | P1 | Platform / Realtime | 單 process demo | Redis session/fan-out、distributed coordination | M4 | Open |
| R-005 | API 與 AI/GPU dependency profile 混合 | 4 | 5 | P1 | Platform / AI | Lazy import 部分降低啟動成本 | Core/API/worker/AI dependency 分離與 gateway | M1/M4 | Open |
| R-006 | 沒有 production CI/deployment/rollback baseline | 5 | 4 | P1 | DevOps | 本機 pytest/shell scripts | CI、container、compose、rollback runbook | M0/M1 | Mitigating |
| R-007 | Kiosk/Admin 無 browser smoke test | 4 | 4 | P1 | Frontend / QA | Backend route/service tests、JS syntax | Playwright critical-path smoke | M3 | Open |
| R-008 | RAG rebuild 在 API process，無 distributed lock | 4 | 4 | P1 | RAG / Platform | Validation、status、alert | Worker job、idempotency、lock、version rollback | M4 | Open |
| R-009 | phone 是會員 PK，PII 未加密 | 5 | 4 | P1 | Identity / Data | Masked output、consent/retention metadata | UUID、tenant hash、encryption、key rotation | M2 | Open |
| R-010 | JSON runtime storage 不適合多 instance | 4 | 5 | P1 | Data / Platform | Atomic replace、thread lock | PostgreSQL durable source、Redis transient state | M2/M4 | Open |
| R-011 | Route 直接碰 repository/provider，boundary 易擴散 | 3 | 4 | P2 | Backend Architecture | 部分 service layer | Module facade、typed schema、architecture test | M1+ | Open |
| R-012 | 672 個 dict/list 型別使用與 raw contract | 3 | 5 | P2 | API Platform | 部分 Pydantic/JSDoc | Pydantic schema、domain type、generated client | M1/M3 | Open |
| R-013 | Admin/Kiosk 大型 JS 與散落 fetch | 3 | 5 | P2 | Frontend | 少量 module、shared client | Feature module、generated client、Vitest | M3 | Open |
| R-014 | Migration timestamp 多為 TEXT，schema scope 不完整 | 4 | 3 | P2 | Data | Version/checksum migration | New typed schema、Alembic、data validation | M2 | Open |
| R-015 | Backup script 存在但沒有定期 restore evidence | 5 | 3 | P1 | DevOps / SRE | pg_dump/pg_restore scripts | Automated backup、encrypted retention、restore drill | M5 | Open |
| R-016 | 外部 AI output 可能產生錯誤或 prompt injection | 4 | 4 | P1 | AI / Security | JSON parser、menu whitelist、RAG guard | Provider-neutral validation、policy enforcement、tool isolation | M1/M4 | Open |
| R-017 | 模型/資料/圖片第三方授權未完成商用確認 | 5 | 3 | P1 | Product / Legal | README 提醒 | License inventory、legal owner、deployment allowlist | Pre-launch | Open |
| R-018 | CORS/token compatibility mode 容易被誤用於 production | 4 | 3 | P1 | Security / DevOps | Production startup validation | Typed settings、secure defaults、deployment policy tests | M1/M2 | Open |
| R-019 | `main.py` thread 啟動雙 Uvicorn loop，不是 production topology | 4 | 4 | P1 | Backend / DevOps | 僅開發使用 | 單 API server/container、Nginx routing、independent frontend | M1 | Open |
| R-020 | Runtime log/interaction data可能包含 PII 或語音內容 | 5 | 3 | P1 | Security / Data | Retention、部分 mask | Data classification、redaction、tenant retention、access audit | M2/M5 | Open |

## Review Cadence

- 每個 Milestone 結束更新 mitigation/status/evidence。
- P0/P1 未有 owner 與 target milestone 時不得 public launch。
- 發現 Secret、跨 tenant data access、不可恢復 migration 或 payment duplicate fulfillment 時，立即視為 release blocker。
