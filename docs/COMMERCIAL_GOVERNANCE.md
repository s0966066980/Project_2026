# Project_2026 商業化治理

- 文件版本：1.0
- 狀態：Active
- 最後更新：2026-07-13
- Owner：Product / Engineering / Operations

本文件定義「可進入商用試點」與「可進入正式營運」的最低門檻。它不是法律意見；隱私、支付、授權與產業法規仍需由對應專業人員確認。

## 1. 環境與發布等級

| 環境 | 用途 | 可使用資料 |
| --- | --- | --- |
| Development | 本機開發與功能驗證 | Mock、匿名或合成資料 |
| Staging | 整合、回歸、部署演練 | 去識別測試資料 |
| Pilot | 受控門市/設備試點 | 經核准的最小必要資料 |
| Production | 正式營運 | 依隱私、保留與權限政策處理 |

Production 不得啟用 demo/test/debug routes，不得使用預設密碼或共用開發 Token。

## 2. 商用 Gate

### Gate A：產品與交易正確性

- 菜單、價格、活動、會員條件與供應狀態由 server 驗證。
- Checkout 不信任前端傳入的價格與優惠結果。
- 訂單具穩定識別碼、狀態與 idempotency 策略。
- 失敗、取消、逾時與重試有明確行為。
- 關鍵點餐流程有 smoke/E2E 驗證。

### Gate B：身分、權限與裝置

- Admin 不共用長期全域 Token；建立 user、role、permission 與 tenant/store scope。
- 高風險操作具權限檢查、二次確認與 audit。
- 每台 Kiosk 具獨立 `device_id` 與可輪替 credential。
- Credential 可撤銷，且不長期存在 URL 或 `localStorage`。
- 離職、設備遺失與 Secret 洩漏有撤銷流程。

### Gate C：資料與隱私

- 商用資料使用 PostgreSQL；JSON 只作開發、測試或受控相容用途。
- 正式 PostgreSQL 商業資料依 ownership 強制 tenant/store/device scope；JSON 只允許 Default Scope 的開發、測試或受控相容流程，不作多租戶隔離邊界。
- 會員使用內部 UUID；手機等 PII 加密保存，查找使用受控 hash/index。
- Consent、privacy version、用途、保留期限、匯出與刪除流程可追蹤。
- Log、trace、error 與 AI prompt 預設遮罩 PII。
- 備份加密，並定期驗證 restore。

### Gate D：應用與基礎設施安全

- Secret 只來自 environment 或 Secret Manager。
- Production 使用 HTTPS、明確 CORS allowlist、security headers 與最小權限。
- Rate limit 在多 instance 環境使用共享儲存，例如 Redis。
- Upload、webhook、URL、檔案路徑與 AI output 均做 schema、大小與權限驗證。
- Dependency、container 與 Secret scanning 納入 CI/CD。
- 建立漏洞分級、修補時限與 incident response owner。

### Gate E：AI、RAG 與模型治理

- 每個 Provider 記錄 model/version、timeout、error、latency 與必要成本指標。
- AI output 不直接成為價格、優惠、付款或高風險操作的唯一真相。
- 菜單、活動與優惠使用白名單/結構化資料驗證。
- RAG 文件具 owner、版本、審核、發布時間與 rollback 能力。
- 模型、權重、資料集、圖片、品牌素材與第三方套件完成商業授權盤點。
- 影像、音訊與情緒資料遵守最小收集、明確告知、用途限制與保留政策。

### Gate F：可靠性與營運

- API、PostgreSQL、Redis/Worker 與大型模型具有清楚 runtime boundary。
- 提供 liveness、readiness 與 dependency health。
- 建立 structured logging、metrics、trace、dashboard 與 alert。
- 定義核心 SLI/SLO：可用性、延遲、checkout 成功率、AI fallback、queue lag。
- 備份、restore、rollback/roll-forward 與災難復原完成演練。
- Kiosk 離線、模型不可用與網路不穩時有 degraded mode。

## 3. 變更分級

| 等級 | 例子 | 最低要求 |
| --- | --- | --- |
| Low | 文件、文案、非關鍵樣式 | 目標檢查、Reviewer |
| Medium | 單一 service、Admin 功能、推薦策略 | 單元/整合測試、相容性檢查 |
| High | Checkout、價格、會員、權限、公開 API | 簡短設計、完整相關測試、Security review |
| Critical | Schema、PII、支付、多租戶、部署拓樸 | ADR、Migration/rollback、Staging 演練、明確核准 |

## 4. Definition of Done

每個變更至少回答：

- 功能與驗收條件是否完成？
- 是否維持既有 API、資料與 UI 相容？
- 是否新增/更新必要測試？
- 是否更新受影響的 README、架構文件、ADR 或 Roadmap？
- 是否檢查 Secret、PII、權限、輸入與 Log？
- 是否執行與風險相稱的驗證，並如實標示未執行項目？
- 是否提供部署、migration、rollback 或操作說明（若適用）？

## 5. 發布決策

發布前由對應 owner 確認：

- Product：功能、文案、流程與營運規則。
- Engineering：程式、測試、相容性、效能與部署。
- Security/Privacy：權限、PII、資料用途與風險。
- AI/RAG Owner：模型、文件版本、fallback 與授權。
- Operations：監控、告警、備份、SOP 與支援窗口。

Critical 變更不得只依單一開發者自我確認進入 Production。
