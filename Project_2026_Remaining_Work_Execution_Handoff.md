# Project_2026 未完成工作執行流程與測試交接手冊

> 狀態：**Canonical remaining-work handoff**
> 建立日期：2026-08-11
> 查證基線：`main@00132a5`，`origin/main@00132a5`；查證開始前 working tree clean，本次交付僅修改／新增文件
> Codex Prompt：[Project_2026_Remaining_Work_Codex_Prompt.md](Project_2026_Remaining_Work_Codex_Prompt.md)
> 原始全程設計：[Project_2026_P2_to_P7_Execution_Plan.md](Project_2026_P2_to_P7_Execution_Plan.md)
> 架構完成度：[Project_2026_Project_Completeness_Roadmap.md](Project_2026_Project_Completeness_Roadmap.md)

## 1. 文件責任

本文件將已完成的 P2 repository work 與真正尚未完成的 Gate 分開，提供另一個 Codex 可直接執行的順序、工作包、測試項目、證據格式與停止條件。

它不重新設計 P2～P7，也不以 Issue 已建立、程式檔存在或 CI 綠燈推論完成。若本文件與舊計畫的狀態欄衝突，以當下 Git、GitHub、CI、同 artifact evidence 與本文件的交接基線重新查證；domain/architecture 決策仍以 `CONTEXT.md` 與 ADR 為準。

## 2. 交接時的嚴格完成狀態

```text
Local Pilot Readiness: BLOCKED — NOT DECLARED（見 3.1 順序例外）
Business Capability Modules passed: 1 / 10
Independent Product Frontends passed: 2 / 2
Current accepted Module Independence Gate: Catalog & Availability
Current active stage: P3 Project Core Brain（Pilot 暫停下的例外路徑）
Project Completion: NOT ACHIEVED
```

> 交接時的原始狀態為 `READY_FOR_HUMAN — NOT DECLARED`。G0.1 已完成並合併（PR #46），G0.2 候選成品證據已記錄；Local Pilot 因憑證移除與缺少目標實機而轉為 `BLOCKED`。

| Stage | Repository／Gate 現況 | 下一個動作 |
| --- | --- | --- |
| P2 repository implementation | PR #40～#43 merged；required checks green | 對照 child issues、補證據、完成 target-device admission |
| Local Pilot | Repository/host evidence recorded；target-device evidence absent | 關閉 Issue #20 與 Pilot security gap |
| P3 | 舊 in-process Project Brain scaffold 存在，非 accepted sidecar | Local Pilot 通過後重構成 sidecar |
| P4 | 無 accepted Optimization Lab module/container | P3 通過後建立 |
| P5.1 | Issues 已建立，Identity/Operations Gate 未通過 | P4 後依序完成兩個 capability |
| P5.2 | Issues 已建立，三個 commercial Gate 未通過 | P5.1 後依序完成 |
| P5.3 | Issue 已建立，Ordering Gate 未通過 | P5.2 後完成 deep module |
| P6 | Issues 已建立，RAG/Voice/Emotion Gate 未通過 | P5.3 後依 dependency 順序完成 |
| P7 | Issue 已建立，legacy closure 未開始 | P6 10/10 candidate 後執行 |

### 2.1 已合併的 P2 證據

- PR #40：Voice Dialogue reducer 與 Emotion contract。
- PR #41：Pilot AI Compose endpoint/mode alignment。
- PR #42：刪除 passive voice recorder legacy。
- PR #43：記錄 repository/host Local Pilot evidence。
- Main CI run `31490505354`：六個 required checks 成功。
- Docker backend：131 passed，2 dependency warnings。
- Dockerized Playwright：5 passed。
- PostgreSQL backup/restore、restart/readiness、R1 readiness、TTS probe、legacy source/bundle checks 已記錄於 `docs/agents/p2-local-pilot-readiness.md`。

這些證據不是 Local Pilot 宣告；只要 application、image、migration 或 external config 改變，就必須判斷並標記 `EVIDENCE_STALE`。

### 2.2 尚未完成的 P2/Pilot 證據

1. 目標 Kiosk 的 microphone、camera、browser permissions、AudioWorklet 與 bundled Silero VAD v5。
2. 250 ms minimum speech、1.2 s ending silence、30 s cap、echo cooldown 與 noisy-store acceptance。
3. 實體 touch/voice ordering、checkout outcome-unknown recovery、Payment Pending handoff。
4. 目標 camera/microphone 的 Live Admin AV Test 與 voice-aligned Emotion evidence。
5. App/worker Pilot container security：read-only root filesystem、`cap_drop: ALL`、必要 writable tmpfs/volumes 與 negative permission evidence。**（Issue #44）**
6. 完成 security/config 修改後的新 candidate artifact 全套重驗。

第 1～4 與 6 需要目標 Kiosk／實機環境，屬 `ready-for-human`。第 5 是本階段唯一 agent-executable 的剩餘工作，由 Issue #44 追蹤。

## 3. GitHub 工作對照

| Issue | 工作 | 交接狀態 | R0 後狀態 |
| --- | --- | --- | --- |
| #18 | P2～P7 Project Completion tracking | Open；總追蹤 | Open；總追蹤 |
| #19 | P2 parent | Open；實作 merged，等待 Gate reconciliation | Open `ready-for-human`；剩餘 scope 全部需實機或人工簽核 |
| #20 | Local Pilot Admission | `ready-for-human`；目前阻塞 | Open `ready-for-human`；新增 #44 為前置 |
| #21 | Voice Dialogue reducer | Open；應補 PR #40 evidence 後判斷關閉 | **Closed**；PR #40 reducer/consumer/red-first tests |
| #22 | Guest/stale artifact closure | Open；應補 PR #40/#42 evidence 後判斷關閉 | **Closed**；PR #40/#42＋zero-use negative test |
| #23 | Silero target-device acceptance | Open；實機部分應保持 `ready-for-human` | Open `ready-for-human`；repository scope 已完成 |
| #24 | Emotion contract/purge | Open；應補 PR #40/#42 evidence，AV 部分連結 #20 | **Closed**；Live AV scope 明確移交 #20 |
| #44 | Pilot container security corrective | 尚未建立 | **New, Open** `ready-for-agent`；G0.1 唯一 agent-executable 剩餘工作 |
| #26 | P3 Project Core Brain | Open；等待 Local Pilot | Open；等待 Local Pilot |
| #30 | P4 Optimization Lab | Open；等待 P3 |
| #25/#31/#27 | P5.1 Identity/Operations | Open；等待 P4 |
| #39/#36/#34/#28 | P5.2 capabilities | Open；等待 P5.1 |
| #29 | P5.3 Ordering | Open；等待 P5.2 |
| #37/#38/#35/#33 | P6 intelligent capabilities | Open；等待 P5.3 |
| #32 | P7 Project Completion | Open；等待 P6 |

Issue 只能在驗收證據回填後關閉。若一個 Issue 同時含 repository 與 target-device scope，應拆分或明確保留未完成 child，不能以 PR merged 直接關閉全部 scope。

## 3.1 順序例外：Local Pilot 暫停（2026-08-11 專案擁有者決定）

本文件第 4 節的固定順序把 P3～P7 全部排在 Local Pilot Admission 之後。2026-08-11 專案擁有者指示移除所有 pilot 登入憑證、目前不建立任何登入認證，並決定**暫停 Local Pilot、先進行 P3～P7 架構收斂**。

```text
Local Pilot Readiness: BLOCKED — NOT DECLARED
阻塞輸入 1：Pilot Configuration Authority（憑證已依指示刪除）
阻塞輸入 2：目標 Kiosk 實機、麥克風、攝影機
決定：明確跨越 Gate 順序，先做 P3～P7
```

這是一個**被記錄的例外，不是通過的 Gate**。後續工作不得以「已進入 P3」推論 Local Pilot 已成立。相關證據與未完成項目見 [`docs/agents/p2-local-pilot-readiness.md`](docs/agents/p2-local-pilot-readiness.md)。

需要恢復 Local Pilot 時的重新進入條件：建立 host-external Pilot Configuration Authority、重建 digest-pinned candidate、重跑第 8 節全部項目，並取得目標實機證據。

## 4. 固定階段順序

```text
R0 — Reconcile handoff and evidence
  ↓
G0 — Local Pilot Security + Target Device Admission
  ↓
P3 — Project Core Brain
  ↓
P4 — Optimization Lab
  ↓
P5.1 — Identity, then Operations & Configuration
  ↓
P5.2 — Member, then Campaign, then Recommendation Analytics
  ↓
P5.3 — Ordering & Checkout
  ↓
P6 — Knowledge/RAG, then Voice, then Emotion
  ↓
P7 — Global legacy closure and full-candidate verification
  ↓
Project Completion
```

前一 Gate 未通過，不得先做下一階段的 implementation。可以盤點後續工作，但不能建立新的 data authority、migration 或 production behavior 來繞過依賴順序。

## 5. 每個工作包共用的修改流程

### 5.1 Preflight

1. 確認 clean working tree、branch、HEAD、`origin/main`、open PR 與 CI。
2. 閱讀 parent/child issues、CONTEXT、相關 ADR 與前一 Gate evidence。
3. 使用 CodeGraph/codebase-memory 建立 symbol、call path、route、repository、consumer 與 test inventory。
4. 補查 configs、Docker、migrations、HTML、generated artifacts、literal routes/settings。
5. 每一項分類：`retain`、`refactor`、`migrate`、`purge`、`generated artifact`。
6. 記錄資料 owner、writers、readers、permission、failure、retention、observability 與 legacy replacement。

### 5.2 Contract and red tests

7. 固定 domain terms、use cases、Capability Interface、HTTP DTO/error/operation ID。
8. 固定 Core/Operational/Optional criticality 與 failure/degradation behavior。
9. 固定 principal、minimum permission、store scope、retention 與 audit。
10. 先建立會失敗的 domain/unit、contract、permission、failure 與 consumer tests。
11. 難逆轉的新決策先更新 ADR；只補清楚詞義時更新 `CONTEXT.md`。

### 5.3 Authority implementation

12. 建立 domain/application/interface/ports/adapters，禁止同 process loopback HTTP。
13. 先讓新 Capability Interface 成為唯一 writer，再遷移 readers。
14. Forward migration 必須支援 fresh install、existing upgrade、idempotent reapply 與 checksum validation。
15. Backfill 後核對 row count、identity、scope、checksum 或 domain-specific reconciliation。
16. 更新 FastAPI/Pydantic OpenAPI，同 commit regenerate TypeScript contract。
17. Admin/Kiosk/worker/other capabilities 全部遷移；不保留手寫 parallel DTO。
18. 加入 readiness、latency、error、degradation、audit 與 legacy usage telemetry。

### 5.4 Zero use and deletion

19. Static architecture tests 證明無 cross-capability repository import/SQL/write。
20. Frontend static tests 證明無 raw legacy route/fetch literal。
21. Runtime telemetry 與 E2E 證明 legacy consumer 為零。
22. 依 replacement → consumer migration → zero use → deletion 的順序移除 legacy。
23. 加入 404/absence/schema/static negative tests，避免舊路徑復活。
24. Material deletion 先解析精確 target；禁止 broad glob、workspace root、home 或未驗證 env variable。

### 5.5 PR and evidence

25. Focused tests → full local supported checks → PR required checks。
26. PR description 記錄 scope/non-scope、authority before/after、migration、failure、security、legacy replacement、recovery 與 evidence。
27. Required checks 全綠後 merge main、刪 branch、回填 Issue/Roadmap/handoff。
28. 判斷後續 change 是否讓先前 evidence stale；需要時立即重跑。

## 6. 通用測試與證據標準

### 6.1 支援命令

核心 Docker runtime：

```bash
docker/scripts/test.sh
docker/scripts/test-ai.sh
```

Frontend：

```bash
cd UI_API/frontend
npm ci
npm run typecheck
npm run syntax
npm run test:coverage
npm run build
npm run test:e2e
```

GPU stack：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up --build -d --wait
```

CPU AI stack：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  up --build -d --wait
```

### 6.2 Required checks

每個 PR 必須通過：

1. Backend Python 3.10。
2. Backend Python 3.12。
3. PostgreSQL migration integration。
4. Redis shared infrastructure integration。
5. Frontend type and syntax checks。
6. Shell syntax checks。

CI frontend job包含 typecheck、build、coverage、syntax、Playwright。CI PostgreSQL job包含 migration status/validate/apply、全 backend tests、reapply、commercial scope、Member integrity、clean migration state。

### 6.3 測試層級

| Layer | 必須證明 |
| --- | --- |
| Domain/unit | invariant、state transition、enum、idempotency、boundary |
| Interface | 跨 capability 呼叫只能使用 published interface |
| HTTP contract | DTO、error、operation ID、permission、404 legacy absence |
| PostgreSQL | fresh、upgrade、reapply、transaction、constraint、reconciliation |
| Redis/outbox/job | TTL、scope、lock、retry、duplicate delivery、dead letter |
| Frontend unit | reducer/controller、DOM/ARIA、failure/retry、no stale state |
| OpenAPI/client | generated contract 無 drift、consumer 不手寫 DTO |
| E2E | 真正 Admin/Kiosk consumer 與 server runtime |
| Docker | build、health、readiness、restart、warm-up、resource permissions |
| Security | principal、store isolation、secret/path/network、read-only/no mutation |
| Retention | raw absence、TTL、expiry、audit、derived reference deletion |
| Hardware/provider | 實際 device/model/credential、no fallback、failure visibility |

SQLite/fake 可用於 unit tests，但不得冒充 PostgreSQL、Redis、filesystem/index、provider 或 target-device integration evidence。

## 7. R0 — 交接與進度治理修正

### 修改流程

1. 驗證 P2 commits `d069068`、`371c5a7`、`f5967a6`、`00132a5` 仍在 main。
2. 核對 PR #40～#43 files、tests、checks 與 evidence doc。
3. 對 #21～#24 建立 acceptance mapping；已完成 scope 補 comment/close，實機 scope 移到或連結 #20。
4. #23 的 target-device VAD 驗收應為 `ready-for-human`，不是 `ready-for-agent`。
5. #19 只有在 P2 Functional Acceptance 與要求的 evidence 完整後關閉。
6. 修正 Roadmap、舊 P2～P7 Plan 的過期狀態與 next gate。
7. 建立 Pilot container security corrective issue，連結 #20。

### 測試/驗證

- `git merge-base --is-ancestor` 驗證 P2 commits 在 main。
- GitHub PR checks 六項 success。
- Working tree clean、docs links valid、`git diff --check`。
- Issue evidence 與實際 PR/commit 一致；沒有「Issue open = not implemented」或「PR merged = all scope passed」的錯判。

### R0 Gate

- Roadmap、handoff、Issues 與 Git/CI 對同一事實一致。
- 所有剩餘 P2/Pilot blocker 有 owner、label、evidence slot。

### R0 執行結果（2026-08-11，基線 `main@00132a5`）

| 驗證項 | 結果 |
| --- | --- |
| `git merge-base --is-ancestor` `d069068`／`371c5a7`／`f5967a6`／`00132a5` | 四個 commit 皆為 `main` 祖先 |
| `origin/main` 與 `HEAD` | 同為 `00132a5` |
| PR #40～#43 | 全部 `MERGED`，merge commits 對應上列四個 commit |
| CI run `31490505354`（`00132a5`） | 六個 required checks 全 `success` |
| P3～P7 新 commits／PRs／Gate evidence | 無；Issue 存在不等於已實作 |
| 過期狀態 | Roadmap 與舊 Plan 的「P2 NOT_STARTED」已修正 |
| Issue 收斂 | #21／#22／#24 關閉並附證據；#23／#19 改 `ready-for-human`；#20 補前置；#44 新建 |

R0 Gate：**PASSED**。

## 8. G0 — Local Pilot Security 與 Target Device Admission

### 8.1 Pilot container security（Issue #44）

#### 修改項目

- 為 Pilot profile 建立明確 Compose overlay，而不是直接把 development `.env` 當 Pilot authority。
- App/worker 使用 non-root user。
- `read_only: true`。
- `cap_drop: [ALL]`；只有觀測證據證明需要時才逐項加回 capability。
- 只為明確 runtime paths 提供 tmpfs 或 scoped writable volumes。
- Secrets 使用 Docker secrets/host-external private source；不得進 image、repository settings、logs 或 API projection。
- Network exposure、diagnostic/debug/demo routes、Redis coordination 與 fail-closed settings 符合 Pilot contract。

#### 測試項目

- Compose config test：app/worker `user` 非 root、rootfs read-only、all caps dropped。
- Container exec：寫 rootfs 必須失敗；寫 allowlisted tmpfs/volume 成功。
- App/worker startup、migration、logs、media temp、model cache、generated reports 不因 read-only 失敗。
- Secret file 可讀但 API/log/env dump 不洩漏內容。
- Debug/demo/ngrok routes disabled。
- Invalid/missing required external config fail fast。
- Restart、health、readiness、worker job/outbox 正常。

### 8.2 新 candidate artifact

Security/Compose 變更會使舊 evidence stale。必須重新記錄：

- Commit SHA。
- App/worker/R1/Ollama/PostgreSQL image digests。
- External config fingerprint。
- Migration head/checksums。
- Target host/runtime identity。
- Evidence collection time。

### 8.3 Target Kiosk tests

#### Device/browser admission

- Device credential provisioning、revocation、store scope。
- Chromium version、camera/microphone permissions、AudioWorklet、local bundled VAD/model assets。
- Reload/restart 後 permission與device state 可恢復。

#### Silero VAD

- 低於 250 ms noise 不建立 Voice Turn。
- 合法 speech 建立一個 turn。
- 1.2 s silence 提交。
- 30 s cap 強制終止。
- TTS期間不監聽；playback 後 cooldown ≤500 ms。
- 十個連續 turns 無重疊、duplicate、track/timer/context leak。
- Background conversation/noisy-store 記錄 false activation 與 missed speech。
- VAD/model/worklet failure 顯示 unavailable，不 fallback RMS/manual activation；touch ordering仍可用。

#### Customer transaction

- Member與Guest入口。
- Catalog/availability。
- Touch cart/quote/confirm。
- Voice candidate/order draft confirmation。
- Duplicate submit/idempotency。
- Network timeout after confirm → Confirmation Outcome Unknown → 查回同一 order。
- Payment Pending handoff 與人工櫃台邊界。
- Cancel、session timeout、Kiosk reset。

#### Admin/Emotion AV

- Live Admin AV Test 2、5、30 seconds。
- Custom prompt與server default reset。
- Result含八欄，fixed emotion/intensity enums。
- Periodic Ordering lifecycle boundary。
- Voice-aligned evidence同一 `voice_turn_id`。
- Camera unavailable不阻擋Voice。
- Raw media/transcript inference後不存在。
- Submitted inference failure產生安全 Undetermined record。
- 30-day TTL以可控clock驗證。

### 8.4 Recovery/operational tests

- PostgreSQL custom-format backup restore到精確temporary database。
- Migration row/checksum/schema reconciliation。
- App/worker/PostgreSQL/Redis restart。
- Optional AI warm-up不阻擋Core HTTP。
- Redis outage：ordering依contract degrade；distributed-lock operation拒絕。
- Pilot Recovery Objective：RPO ≤1 hour、RTO ≤4 hours 的觀測證據。

### G0 Gate

所有測試使用同一 candidate；通過後宣告 Local Pilot Readiness、關閉 #19/#20/相關 P2 children、更新 evidence，才進 P3。

## 9. P3 — Project Core Brain

### 9.1 現況與目標

現有 `project_brain_routes.py`、`project_brain_service.py`、Admin functions 與 tests 是 in-process scaffold。P3 Gate 要求獨立 `project-analyst` sidecar；不能把現有 `_generate()` thread call 當完成。

### 9.2 修改工作包

1. Inventory：現有 routes/service/storage/UI/tests、provider calls、filesystem reads、recommendation target settings。
2. 移除「推薦表現目標」UI/settings/consumer；合法 analytics 留給 P5.2 authority。
3. 固定 UI API ↔ sidecar request/status/report contracts。
4. 建立 sanitized Project Analysis Snapshot builder，只讀 allowlist evidence。
5. 建立 sidecar image、non-root/read-only/cap-drop/resources/timeout/network/secret mounts。
6. Provider profiles：Codex/Claude/Grok version/auth/headless/read-only/schema probes。
7. Manual analyze/reanalyze；一次明確一個 ready profile，無 fallback。
8. Latest successful report atomic replace；failed rescan保留舊report並標 stale。
9. Proposal workflow：disposable isolated worktree，documents只在`docs/proposals/`、extensions只在`extensions/<name>/`，不apply/commit/push。
10. 刪除 UI API process 中的任意 filesystem/shell/provider execution path。

### 9.3 測試項目

- Snapshot allowlist正向測試。
- `.env`、secret、home、external path、symlink/path traversal、DB/raw media拒絕。
- No Docker socket、no arbitrary shell、network allowlist。
- Container rootfs write失敗、non-root、caps dropped、resource/time limit。
- Provider unsupported version、missing credential、malformed JSON、schema mismatch、timeout。
- Selected provider failure不切換其他provider。
- Concurrent analyze dedup/refusal。
- Successful rescan atomic replace；舊report永久移除。
- Failed rescan保留old report + stale safe error。
- Active workspace tree/hash在proposal前後不變。
- Proposal path escape、existing core file modification、forbidden dependency拒絕。
- Proposal expiry/rejection清除isolated artifacts。
- Admin permission、store/project scope、restart與frontend failure/retry。

### P3 Gate

Sidecar isolation、provider readiness、evidence allowlist、latest-report atomicity、proposal no-apply、Admin consumer與Docker evidence同artifact通過；更新Issue #26後進P4。

## 10. P4 — Optimization Lab

### 10.1 修改工作包

1. 建立與Project Analyst分離的module/container與data store。
2. 建立Voice Interaction Evidence pre-persist irreversible redaction。
3. 建立30-day evidence TTL、encryption-at-rest interface、store scope與audit。
4. 建立單店單日Daily Evidence Snapshot；today標partial/cutoff，IDs frozen。
5. 建立Codex/Claude/Grok provider-native model/effort discovery；single analyzer、no fallback。
6. Fixed classification與1–2 observation/≥3 or reproducible guidance threshold。
7. Voice/RAG offline acceptance sandbox。
8. Fixed six-section reference-only report，只引用opaque evidence IDs。
9. `optimization.evidence.read` + 15-minute step-up與per-expansion audit。
10. Provider-specific customer-evidence authorization/credential/disclosure/retention/egress audit。
11. API、network、mounts與credentials強制no production mutation。

### 10.2 測試項目

- Raw audio/member/device/session/order/payment/individual emotion永不persist。
- PII redaction成功；無法redact就discard。
- Cross-store evidence/query拒絕。
- Current-day cutoff與historical full-day timezone boundary。
- Run開始後新evidence不進snapshot。
- Analyzer unsupported model/effort在egress前拒絕。
- Analyzer failure無fallback。
- 1、2筆只Observation；3筆相似或synthetic reproducible才Reference Guidance。
- Contradictory evidence → Insufficient Evidence。
- Offline acceptance regression → guidance rejected/unverified。
- Report無transcript/answer copy。
- Expired evidence reference unavailable；report/evidence TTL及derived index刪除。
- Summary permission、step-up expiry、audit content不含conversation。
- Synthetic-only default；missing customer authorization阻擋egress。
- Settings/RAG/Campaign/Recommendation/filesystem/DB mutation API absence與negative tests。

### P4 Gate

Reference-only、privacy、authorization、TTL、classification、offline acceptance、provider egress與container isolation全部通過；更新Issue #30後進P5.1。

## 11. P5.1 — Identity 與 Operations & Configuration

### 11.1 Identity & Device Access（Issue #25）

#### 修改項目

- 盤點`admin_*`、`device_*`、`devices`、`fleet_*`writers/readers。
- 建立唯一Identity Capability Interface與versioned HTTP API。
- 收斂device/admin principals、sessions、RBAC、credentials、fleet access、audit。
- 遷移跨模組global services/repository imports。
- Legacy principal/scope compatibility telemetry zero後刪除。

#### 測試

- Credential provision/rotate/revoke/expire。
- Device/Admin anonymous boundaries與least permission。
- Store isolation、wrong-device/wrong-store拒絕。
- Session restart/expiry/replay。
- Audit complete但不含secret。
- PostgreSQL unique/foreign-key/concurrency/migration。
- Admin/Kiosk generated-client consumers。
- Legacy routes/imports/SQL/static/telemetry zero。
- Core failure closed。

### 11.2 Operations & Configuration（Issue #31）

#### 修改項目

- 收斂commercial settings、audit、capability status、health/readiness與operator actions。
- 取代`config/profiles/local-pilot.env.example`。
- 將`UI_API/deploy/postgres`能力移至canonical`docker/`。
- 將`learning_data/settings.json`正式設定移入Operations authority；tests移fixtures。
- Admin raw fetch改generated client與bounded failure UX。

#### 測試

- Settings version/concurrency/validation/rollback projection。
- External config required/missing/secret leakage。
- Fresh/upgrade PostgreSQL role/init/WAL/backup。
- Core readiness vs Optional warm-up。
- Redis/shared-infrastructure degradation。
- Health timeout、operator retry、audit。
- Admin raw fetch/static route literals歸零於此scope。
- Old deploy/profile/settings paths negative tests。

### P5.1 Gate

Identity與Operations各自通過十項Module Independence Gate；parent #27才能關閉並進P5.2。

## 12. P5.2 — Member、Campaign、Recommendation Analytics

### 12.1 Member（Issue #39）

修改：members、consent、preferences、session/history唯一owner；Guest ordering不依賴Member ready。

測試：

- Member register/login/not-found/retry。
- Consent opt-in/out/version/retention。
- PII encryption/key failure/redaction。
- Member session expiry/store isolation。
- History consent與guest absence。
- Member dependency unavailable時Guest flow成功。
- PostgreSQL migration/backfill/integrity/concurrency。
- Admin/Kiosk consumers與legacy repository/route zero。

### 12.2 Campaign & Promotion（Issue #36）

修改：Campaign lifecycle/version/publication、promotion rule、push copy、active projection唯一owner，刪legacy promotion parallel truth。

測試：

- Allowed/forbidden lifecycle transitions。
- Content edit不改lifecycle；publication atomic。
- Schedule timezone/start/end。
- Promotion price validation與server authority。
- Campaign/Base push copy resolution。
- Unverified promotion claim rejected。
- Concurrent edit/version conflict。
- Kiosk只讀active projection。
- Legacy promotion route/table/consumer telemetry zero。

### 12.3 Recommendation & Interaction Analytics（Issue #34）

修改：decision/events、commercial touch、interaction/effectiveness analytics唯一owner；刪除推薦表現目標殘留。

測試：

- Eligibility/availability/cart exclusion。
- Placeholder不產生commercial touch。
- Duplicate/replay event idempotency。
- Voice/recommendation/campaign attribution。
- Store scope、retention、event ordering。
- Accepted metrics definitions reach Admin。
- Removed target settings/UI/API negative tests。
- Member/Campaign只透過published interface/read model。
- Legacy analytics repositories/routes/raw fetch zero。

### P5.2 Gate

三個capability各自Gate通過，parent #28關閉後進P5.3。

## 13. P5.3 — Ordering & Checkout（Issue #29）

### 修改工作包

1. Inventory Entry/Session/Cart/Quote/Confirmation/Order/Payment Pending writers/readers。
2. 建立Ordering deep-module interface/API/domain/ports/adapters。
3. Server-only pricing/availability revalidation/quote/order authority。
4. 跨能力使用Member/Campaign/Recommendation/Catalog published contracts。
5. 保留idempotency、Confirmation Outcome Unknown、transactional outbox、manual payment boundary。
6. Consumer migration與legacy route/service/repository deletion。

### 測試項目

- Entry Flow transition/resume/timeout/revision。
- Guest/Member choices與policy load timeout fallback。
- Cart add/update/remove、availability、quantity、scope。
- Server pricing、promotion、fee、currency與browser tampering拒絕。
- Quote snapshot/version/expiry/stale quote。
- Confirmation idempotency與duplicate submit。
- Timeout after commit → same-order recovery。
- Sold out/price changed/dependency degraded。
- Transaction rollback、outbox atomicity、retry/dead letter。
- Order identity、history、Payment Pending handoff。
- Restart during confirmation/recovery。
- Full touch/voice E2E。
- AI/browser/cross-capability SQL無transaction write authority。
- Legacy cart/checkout/order API/consumer/telemetry zero。

### P5.3 Gate

Ordering Module Independence十項全通過後進P6。

## 14. P6 — Intelligent Capabilities

順序固定為Knowledge/RAG → Voice → Emotion。P2 UX與records是frozen behavior contract。

### 14.1 Knowledge/RAG（Issue #37）

修改：Knowledge lifecycle、publication attempts、published pointer、retrieval configuration/checks、index artifacts唯一owner；worker走durable jobs/outbox。

測試：

- Store isolation與knowledge CRUD/version conflict。
- Atomic publish；index/publication failure保留old published pointer。
- Durable job retry/resume/dead letter/restart。
- Retrieval config唯一published、invalid delete/restore。
- RAG check evidence expires onindex/config change。
- Provider/model unavailable、timeout、no fallback。
- Admin generated client與legacy review/import/readiness paths zero。
- Index path permissions、checksum、retention/rebuild。

### 14.2 Voice Assistance（Issue #38）

修改：Voice Turn journal、STT/LLM/TTS orchestration、candidate set、order draft proposal、playback outcome、interaction evidence唯一owner；Silero browser adapter維持Kiosk consumer。

測試：

- Turn ID/store/session scope、state transitions。
- Retry/replay不重做assistant或duplicate draft。
- STT/LLM/TTS timeouts與explicit failure。
- Success必須有playable TTS；playback failure保留text但非success。
- Camera degradation不阻擋Voice。
- Candidate menu allowlist、ambiguous choices、no auto cart mutation。
- P95 response wait與warm-up refusal。
- 30-day de-identified Voice Interaction Evidence TTL。
- P2 dialogue order/VAD frozen regression。
- `/api/ask*`、passive recorder、side writes、direct repository imports zero。

### 14.3 Emotion Diagnostics（Issue #35）

修改：P2 model profiles、readiness、modes、capture、live test、records/TTL收斂為Emotion capability；R1只作adapter。

測試：

- P2三模式、clip duration與ordering boundary regression。
- Readiness與configured mode分離。
- No concurrent backlog。
- Voice-aligned AV與unvalidated audio-only skip。
- Submitted failure safe record。
- Eight fields/fixed enums/store scope/30-day TTL。
- Raw media/transcript absence。
- Advisory-only：Voice/Recommendation/Pricing/Ordering不被修改。
- R1 unavailable只degrade Emotion。
- ADR-0057 legacy paths不復活。
- Admin/Kiosk generated client與legacy routes/repositories zero。

### P6 Gate

三個capability各自通過Module Independence Gate後，實際計數應達10/10；parent #33通過才進P7。

## 15. P7 — Legacy Closure 與 Project Completion（Issue #32）

### 15.1 Zero-use inventory

- Admin/Kiosk feature source raw `fetch` zero；transport implementation只在shared generated layer。
- Compatibility `/api/*` static consumers與runtime telemetry zero。
- Cross-capability repository import、SQL/write、global service、internal HTTP loopback zero。
- Legacy settings、tables/columns、jobs、fixtures、flags、allowlists、import exceptions與generated artifacts有replacement/deletion evidence。
- P2～P6 convergence debt zero blocking items。

### 15.2 Final deletion

- 刪除giant `v1_routes.py`；不得原封不動搬成另一巨檔。
- 刪除已空horizontal `routes/services/repositories/modules`。
- 刪除temporary architecture allowlists、compatibility adapters/counters與migration-only runtime code。
- 保留migrations、ADR、audit與必要歷史。

### 15.3 Full-candidate test matrix

同一commit/digests/config/migration/environment執行：

1. Clean CI build與digest pinning。
2. Fresh install migration、existing upgrade、reapply、checksum/reconciliation。
3. Backend Python 3.10/3.12、Ruff、format、mypy、all tests。
4. PostgreSQL與Redis integration。
5. Frontend typecheck、syntax、coverage、build、Playwright。
6. Architecture imports、raw fetch、legacy literal、OpenAPI drift。
7. Device/Admin auth、store scope與permissions。
8. Member/Guest/Catalog/Campaign/Recommendation flows。
9. Touch/Voice Ordering、Checkout unknown outcome、Payment Pending。
10. RAG publish/retrieval/recovery。
11. Emotion modes/live AV/retention。
12. Project Analyst isolation/proposals/providers。
13. Optimization evidence/privacy/reports/egress。
14. Docker read-only/cap-drop、restart/warm-up/degradation。
15. Backup/restore與Pilot Recovery Objective。
16. Target Kiosk VAD/noisy-store/STT/LLM/TTS/camera/soak。
17. Secret/path/network/provider egress與audit。
18. Raw-media absence與所有30-day TTL。
19. Legacy telemetry zero。
20. Ten Module Independence evidence sets與Admin/Kiosk 2/2。

### P7 Gate

```text
Local Pilot Readiness: DECLARED for current artifact
Business Capability Modules passed: 10 / 10
Independent Product Frontends passed: 2 / 2
Legacy compatibility usage: ZERO
P2–P7 convergence debt: ZERO blocking items
P7 full-candidate verification: PASSED
Project Completion: ACHIEVED
```

## 16. Evidence ledger template

每個Gate使用：

| Field | Value |
| --- | --- |
| Stage / capability | |
| Status | NOT_STARTED / IN_PROGRESS / BLOCKED / EVIDENCE_STALE / PASSED |
| Issue / PR | |
| Commit | |
| Image digests | |
| Config fingerprint | |
| Migration head / checksums | |
| Runtime / hardware | |
| Focused tests | |
| Full required checks | |
| Failure/degradation evidence | |
| Security/retention evidence | |
| Consumer/legacy zero evidence | |
| Recovery/rollback/forward repair | |
| Remaining debt | |
| Evidence timestamp | |

完成度不記錄主觀百分比。後續變更影響任何欄位時，Gate改成`EVIDENCE_STALE`並重跑。

## 17. 真實阻塞與交接規則

以下缺失可能需要`ready-for-human`：target hardware、GPU/camera/microphone、provider automation credentials、customer-evidence authorization、manager step-up、external Pilot config、backup target、GitHub permission。

遇到阻塞時：

1. 完成所有不依賴該輸入的工作。
2. 記錄精確Gate、已完成證據、缺少輸入與不可替代原因。
3. 不偽造、不fallback、不把blocked改passed。
4. 若它阻擋固定順序，停止並請使用者提供；不得跳階段。

## 18. Codex 最終交付格式

最終回覆必須列出：

- 每個Stage/Gate最終狀態。
- Local Pilot與Project Completion結論。
- 10/10 modules與2/2 frontends證據。
- Issues、PRs、commits、merged/deleted branches。
- Migrations/backfills/purges與recovery evidence。
- Focused、required、Docker、E2E、hardware/provider tests。
- Digests、config fingerprint、migration head。
- Legacy usage與convergence debt。
- 所有remaining `ready-for-human` blockers。

只有P7 Gate完整通過或固定順序遇到真實外部阻塞時，執行Codex才可停止。
