# Project_2026 Remaining Work — Codex 交付 Prompt

> 建立日期：2026-08-11
> 已知交接基線：`main@00132a5`
> 使用方式：將下方「Prompt 開始」至「Prompt 結束」完整貼入新的 Codex 對話。
> 詳細流程與測試權威：[Project_2026_Remaining_Work_Execution_Handoff.md](Project_2026_Remaining_Work_Execution_Handoff.md)

---

## Prompt 開始

你正在處理 `/home/oliver/Project_2026`。

你的任務不是重新規劃，也不是只完成一個階段；請從目前尚未通過的 Local Pilot Admission 開始，依序完成 Local Pilot、P3、P4、P5.1、P5.2、P5.3、P6、P7，直到 Project Completion Gate 通過。

不要重做已合併的 P2 repository implementation。先驗證交接事實，再修正缺口。除非遇到缺少使用者授權、credential、目標硬體或外部狀態而確實無法繼續的阻塞，否則不得停在分析、計畫、單一 PR 或中間階段。

### 1. 開始前必讀

完整閱讀並遵守：

1. `/home/oliver/Project_2026/AGENTS.md`
2. `/home/oliver/Project_2026/Project_2026_Remaining_Work_Execution_Handoff.md`
3. `/home/oliver/Project_2026/Project_2026_Project_Completeness_Roadmap.md`
4. `/home/oliver/Project_2026/Project_2026_P2_to_P7_Execution_Plan.md`
5. `/home/oliver/Project_2026/CONTEXT.md`
6. `/home/oliver/Project_2026/docs/agents/issue-tracker.md`
7. `/home/oliver/Project_2026/docs/agents/triage-labels.md`
8. `/home/oliver/Project_2026/docs/agents/domain.md`
9. 每個階段引用的 `docs/adr/` 決策。

`Project_2026_Remaining_Work_Execution_Handoff.md` 是目前未完成工作的 canonical handoff；舊計畫保留原始設計與歷史。若狀態敘述衝突，以 Git、GitHub、CI、同 artifact 證據與 handoff 為準，並在第一個文件 PR 修正漂移。

### 2. 必須先驗證的交接事實

不要直接相信本 Prompt；先用唯讀檢查確認：

- branch、HEAD、`origin/main` 與 `git status`。
- 最近 commits、open Issues、PRs、required checks 與 workflow runs。
- migration head、Docker Compose config、current image digests 與 readiness evidence。
- P2 PR #40～#43 是否仍在 main 且 CI 綠燈。
- `docs/agents/p2-local-pilot-readiness.md` 是否仍對應目前 application/image/migration/config。
- Issue #20 的 target-device blockers 是否仍未完成。
- P3～P7 是否有新 commits、PRs 或 Gate evidence；不能只看 Issue 是否存在。

已知狀態是：

```text
Working tree: clean
HEAD/origin-main: 00132a5
P2 repository implementation: merged
Local Pilot Readiness: READY_FOR_HUMAN — NOT DECLARED
Business Capability Modules passed: 1 / 10
Independent Product Frontends passed: 2 / 2
P3–P7: no accepted Gate evidence yet
```

若查證後已改變，記錄新的基線並依實際狀態繼續，不重做已通過且證據仍有效的 Gate。

### 3. Code discovery

Repository 有 CodeGraph／codebase-memory 時優先使用：

1. `search_graph`
2. `trace_path`
3. `get_code_snippet`
4. `query_graph`
5. `get_architecture`

只有搜尋字串、HTML、設定、Docker、migration、文件或 graph 不足時才使用 `rg`。已有檔案、route、service、module、test 或 Issue 不算完成；每個現況先分類為 `retain`、`refactor`、`migrate`、`purge` 或 `generated artifact`。

### 4. 工作與 GitHub 授權

你可以在本任務範圍內：

- 建立、更新與關閉 GitHub Issues。
- 調整五個 triage labels：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。
- 建立 short-lived branches、commits、push 與 PR。
- 等待並修正 required checks。
- Checks 全綠且 Gate evidence 完整後 merge main 並刪除 branch。
- 更新 Roadmap、handoff、CONTEXT、ADR 與 evidence files。

限制：

- 一個 PR 不跨兩個 capabilities 的 data ownership。
- Mechanical move 與 behavior change 分開。
- 不得回退使用者變更。
- 不得使用 `git reset --hard`、廣泛 checkout 或未解析的 destructive glob。
- 不得刪除 PostgreSQL volumes、backups、secrets 或未授權 customer/business data。
- 不得因測試困難而跳過 Gate 或改成主觀完成百分比。

### 5. 執行順序

必須依序完成，前一 Gate 未通過不得跳到後面：

```text
R0 交接與狀態修正
  → Local Pilot Admission
  → P3 Project Core Brain
  → P4 Optimization Lab
  → P5.1 Identity / Operations & Configuration
  → P5.2 Member / Campaign / Recommendation
  → P5.3 Ordering & Checkout
  → P6 Knowledge/RAG / Voice / Emotion
  → P7 Legacy Closure / full-candidate verification
  → Project Completion
```

每個階段的修改流程、測試清單、evidence slots、Issue 對照與完成條件全部依 `Project_2026_Remaining_Work_Execution_Handoff.md` 執行。

### 6. R0 — 先修正進度治理

開始任何新產品功能前：

1. 對照 PR #40～#43 與 P2 child Issues #21～#24。
2. 已由合併證據完成的 child issue，補上 PR/commit/tests 後關閉；仍依賴實機的 #23 保持或改成 `ready-for-human`。
3. Parent Issue #19 在 P2 Functional Acceptance 真正成立前不得關閉。
4. Issue #20 保持 `ready-for-human` 直到同 artifact target-device admission 完成。
5. 修正 Roadmap 與舊 Execution Plan 中「P2 未開始」的過期狀態。
6. 將 app/worker 尚未 read-only root filesystem、未 `cap_drop: ALL` 的 Pilot security gap 建立明確 corrective issue；依 handoff 完成或取得明確接受決策，不能藏在備註中。

### 7. Local Pilot Admission

先關閉 Issue #20 與 Pilot security gap：

- 建立 Pilot-specific Compose/security contract；app/worker non-root、read-only root filesystem、dropped Linux capabilities，只開必要 writable tmpfs/volumes。
- 使用 host-external secrets/config，不以 repository `.env` 建立 Pilot readiness。
- Security/Compose 修改會使舊 P2 artifact evidence stale；建立新的 digest-pinned candidate，重跑 repository-verifiable admission。
- 在目標 Kiosk 驗證 microphone、camera、browser permissions、AudioWorklet、bundled Silero VAD v5、250 ms speech、1.2 s silence、30 s cap、echo cooldown、noisy-store behavior 與 cleanup。
- 在目標設備驗證 touch/voice ordering、checkout outcome unknown、Payment Pending handoff。
- 驗證 Live Admin AV Test 與 voice-aligned Emotion evidence；raw media 不落地。
- 重跑 migration、backup/restore、restart/warm-up/degradation、security、Docker、backend、frontend、Playwright、AI/GPU tests。
- 所有證據必須屬於同一 commit、image digests、config fingerprint、migration head 與 target environment。

全部通過才可：

- `Local Pilot Readiness: DECLARED`
- 關閉 #19、#20 與剩餘 P2 child issues。
- 更新 readiness evidence 與 Roadmap。
- 進入 P3。

### 8. P3～P7 核心範圍

P3：完成獨立 `project-analyst` sidecar、provider readiness、evidence allowlist、latest-report atomicity、isolated proposal worktree，移除舊「推薦表現目標」。現有 in-process `project_brain_service` 只是 scaffold，不符合 Gate。

P4：建立獨立 reference-only Optimization Lab、去識別化 Voice Interaction Evidence、單店單日 snapshot、provider-native analyzer options、classification/evidence threshold、offline acceptance、step-up/audit、TTL 與 no-production-mutation enforcement。

P5.1：Identity & Device Access 和 Operations & Configuration 各自通過 Module Independence Gate；完成 external Pilot config、canonical Docker/PostgreSQL runtime、settings authority 與 Admin generated-client migration。

P5.2：依序完成 Member、Campaign & Promotion、Recommendation & Interaction Analytics Module Independence Gate。

P5.3：將 Entry、Session、Cart、Quote、Confirmation、Order、Payment Pending 收斂成 Ordering transaction deep module，保留 server pricing、idempotency、outcome recovery 與 outbox。

P6：依 Knowledge/RAG → Voice Assistance → Emotion Diagnostics 完成三個 intelligent capability Gate；P2 customer behavior 是 frozen contract，不能被架構重構暗中改寫。

P7：raw frontend fetch、compatibility API usage、cross-capability repository/SQL/write、legacy allowlists 全部歸零；刪除 giant `v1_routes.py`、已空 horizontal folders 與 compatibility paths，完成同 artifact 全候選成品驗證。

### 9. 通用測試命令

每個 PR 依影響範圍執行 focused tests，再執行支援的完整 checks。最低基線：

```bash
docker/scripts/test.sh
docker/scripts/test-ai.sh

cd UI_API/frontend
npm ci
npm run typecheck
npm run syntax
npm run test:coverage
npm run build
npm run test:e2e
```

GitHub required checks 必須全綠：

- Backend Python 3.10
- Backend Python 3.12
- PostgreSQL migration integration
- Redis shared infrastructure integration
- Frontend type and syntax checks
- Shell syntax checks

不能用 SQLite/in-memory fake 冒充 PostgreSQL、Redis、filesystem/index/provider integration evidence。

### 10. 完成與證據規則

每個 Gate 必須記錄：

- Issue、PR、commit。
- Image digests。
- Migration head 與 reconciliation。
- Config fingerprint。
- Tests 與實際結果。
- Runtime/hardware/environment。
- Legacy replacement 與 zero-use evidence。
- Security/retention/failure evidence。
- Remaining convergence debt。

如果後續變更影響舊證據，將狀態改為 `EVIDENCE_STALE` 並重跑。不得保留 `PASSED` 只加一句備註。

### 11. 真實阻塞

若缺少 target hardware、GPU/camera/microphone、provider credential、customer-evidence authorization、manager step-up、GitHub permission、external Pilot config 或 backup target：

1. 完成所有不依賴該條件的工作。
2. 記錄精確 Gate、已完成證據、缺少輸入與不可替代原因。
3. 將 Issue 標 `ready-for-human`。
4. 如果它阻擋階段順序，停止並詢問使用者；不得跳到後續階段。

不得偽造、推測或降級證據，也不得自動 provider/model fallback。

### 12. 最終完成條件

只有以下全部成立才結束：

```text
Local Pilot Readiness: DECLARED for current artifact
Business Capability Modules passed: 10 / 10
Independent Product Frontends passed: 2 / 2
Legacy compatibility usage: ZERO
P2–P7 convergence debt: ZERO blocking items
P7 full-candidate verification: PASSED
All required checks: PASSED
Project Completion: ACHIEVED
```

不要使用主觀百分比。

最終回覆列出每個 Gate、Issues、PRs、commits、migrations、purges、tests、Docker/hardware evidence、image digests、legacy-zero evidence、remaining blockers，並明確說明是否真正達到 Project Completion。

## Prompt 結束
