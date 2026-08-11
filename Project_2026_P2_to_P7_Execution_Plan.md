# Project_2026 P2～P7 完整修改與收斂執行計畫

> 狀態：**原始全程設計；P2 repository work 已合併，當前剩餘工作由 handoff 接續**
> 建立日期：2026-08-11
> 原始規劃基線：`main@3dd51f4`；目前查證基線：`main@00132a5`
> 當前執行權威：[Project_2026_Remaining_Work_Execution_Handoff.md](Project_2026_Remaining_Work_Execution_Handoff.md)
> Codex Prompt：[Project_2026_Remaining_Work_Codex_Prompt.md](Project_2026_Remaining_Work_Codex_Prompt.md)
> 架構與既有完成證據：[Project_2026_Project_Completeness_Roadmap.md](Project_2026_Project_Completeness_Roadmap.md)
> Domain language：[CONTEXT.md](CONTEXT.md)
> 決策歷史：[docs/adr/](docs/adr/)

## 1. 文件責任與完成邊界

本文件是 P2 之後的 **canonical execution plan**，負責回答：以什麼順序修改、每次修改包含哪些工作、如何遷移與刪除舊路徑、需要哪些測試與證據，以及何時才可進入下一階段。

Roadmap 保留架構目標、已完成歷史與 Gate 證據；本文件負責 P2～P7 的未來執行細節。兩份文件若出現衝突，以 ADR 與 `CONTEXT.md` 的已接受決策為上位約束，並在同一個 PR 修正兩份文件，不允許長期雙軌漂移。

本計畫有兩個不同終點：

1. **第一終點 — Local Pilot Readiness**：P2 通過功能 Gate 後，以同一個 Pilot Release Artifact 執行完整 admission。只有 runtime、contract、customer transaction、intelligent capability、security 與 recovery 證據全部有效時才可宣告；「P2 功能完成」不會自動等於 Pilot Ready。
2. **第二終點 — Project Completion**：P7 通過後，十個 Business Capability Modules 為 `10/10`、Admin/Kiosk 為 `2/2`、legacy usage 歸零且舊路徑已安全刪除。這是本文件的最終完成條件。

Local Pilot Readiness 不代表 production HA、跨店部署或自動電子付款完成；那些不在本計畫授權範圍。

## 2. 統一編號與舊 Roadmap 對照

舊 Roadmap 同時使用 Batch P2～P4 與 Phase 3～7。自本文件起，未完成工作統一使用 P2～P7：

| 新執行階段 | 內容 | 舊 Roadmap 對照 | 前進 Gate |
| --- | --- | --- | --- |
| P2 | Kiosk Voice UX、Silero VAD v5、Emotion Diagnostics 重構 | Batch P2，加上本輪新增 Kiosk 目標 | P2 Functional Acceptance＋Pilot Admission |
| P3 | Project Core Brain 與舊推薦目標移除 | Batch P3 | P3 Functional Acceptance |
| P4 | Optimization Lab（reference-only） | Batch P4 | P4 Functional Acceptance |
| P5.1 | Identity & Device Access；Operations & Configuration | Phase 3 | 各 capability 的 Module Independence Gate |
| P5.2 | Member；Campaign & Promotion；Recommendation & Interaction Analytics | Phase 4 | 各 capability 的 Module Independence Gate |
| P5.3 | Ordering & Checkout transaction deep module | Phase 5 | Ordering Module Independence Gate |
| P6 | Knowledge/RAG → Voice Assistance → Emotion Diagnostics | Phase 6 | 三個 intelligent capability 的 Module Independence Gate |
| P7 | legacy closure、完整候選成品驗收與結案 | Phase 7 | Project Completion Gate |

Phase 0～2 已完成，不重新編號，也不重做其歷史工作。

## 3. 嚴格現況基線

```text
Primary delivery endpoint — Local Pilot Readiness: READY_FOR_HUMAN — NOT YET DECLARED
Business Capability Modules passed: 1 / 10
Independent Product Frontends passed: 2 / 2
Current completed vertical slice: Catalog & Availability
P2 repository implementation: MERGED — PR #40 through #43
Next executable gate: Local Pilot target-device and security admission
```

「已有檔案、route 或測試」只代表存在雛形，不代表 Gate 通過。P2 開工前必須把現況逐項分類成 `retain`、`refactor`、`migrate`、`purge` 或 `generated artifact`：

- `kiosk/voice.js` 已有串流 Voice Turn、部分 Silero 與自動恢復監聽路徑；必須稽核事件順序、模型資產、舊 RMS/passive recorder 與實機行為，不能從零另建第二套語音流程。
- Kiosk source 已沒有「略過，直接點餐」，但舊 `dist/kiosk/app.js.map` 仍可找到字串；P2 要重建產物並以 source、bundle、source map 與 E2E 四層證明舊入口消失。
- Emotion service、Admin UI、legacy influence/effectiveness functions 與 routes 同時存在；P2 是權威模型替換與永久清除，不是只在舊頁上隱藏控制項。
- `project_brain_routes.py`、`project_brain_service.py` 與 `test_project_brain.py` 已存在 in-process scaffold；P3 必須依 sidecar ADR 判斷可保留 contract、需遷移執行或需刪除的部分。
- 尚未發現獨立 Optimization Lab module/container；P4 視為需建立的新隔離能力，但不得重用 recommendation effectiveness report 冒充。
- `__pycache__`、`dist`、source maps 等可重建內容不是權威來源，不能作為功能完成證據。

## 4. 所有階段共用的修改流程

每個 P 階段與每個 capability 都必須依序走完下列流程。可以拆成多個短 PR，但不得跳過步驟。

### 4.1 啟動與盤點

1. 從本文件對應工作包建立 GitHub parent issue 與可驗收 child issues；標示資料 owner、呼叫者、前置依賴、風險與明確不做事項。
2. 使用 CodeGraph／codebase knowledge graph 盤點定義、call path、route、repository、frontend consumer 與 tests；字串、設定與非程式檔再用 literal search 補查。
3. 建立 as-is inventory：API、資料表、設定、權限、事件、background job、Docker volume、UI、generated artifacts、legacy callers、runtime telemetry。
4. 對每一項標記 `retain/refactor/migrate/purge`，並記錄 canonical replacement。無 replacement 的 legacy 項目不得先刪。

### 4.2 契約與失敗先行

5. 在實作前固定 domain term、use case、principal/permission、資料權威、HTTP DTO/error code、retention、failure/degradation 與 observability contract。
6. 先加入會失敗的 domain/unit、contract、permission、failure 與 consumer tests；行為變更與純 mechanical move 分開。
7. 若決策難逆轉、出乎預期且有真實 trade-off，先新增或修訂 ADR；只補術語時更新 `CONTEXT.md`，不建立重複 ADR。

### 4.3 權威實作與遷移

8. 建立或收斂 domain/application/interface/ports/adapters；同 process 跨能力只走 Capability Interface，out-of-process caller 只走 versioned HTTP contract。
9. 先讓新 interface 成為唯一寫入 authority，再遷移 read consumers；禁止新舊路徑各自保留 business rules。
10. 資料結構變更使用 forward migration、backfill/reconciliation 與明確失敗策略；在 cutover 前鎖定 row count、checksum、owner 與 restore/forward-recovery 證據。
11. FastAPI/Pydantic 更新 OpenAPI，同 commit 重新產生 TypeScript client；Admin/Kiosk feature 不手寫平行 DTO 或 raw transport contract。
12. 更新 Docker Compose、external configuration、health/readiness、resource bounds、audit 與 telemetry；host Python/Conda 結果不得作為完成證據。

### 4.4 Consumer cutover、零使用與刪除

13. Admin、Kiosk、worker 與跨能力 caller 全部切換到新契約；legacy route 只能暫時轉接到權威 interface，並必須計量 usage。
14. 先以 static search、architecture tests、generated client checks、runtime telemetry 與 E2E 證明舊 consumer 歸零。
15. 再刪除 legacy UI、route、service、repository、table/column、setting、allowlist、fixture 與 generated artifact；刪除後加入 negative contract test 防止復活。
16. 同一 artifact 執行 migration、restart、smoke、failure 與 retention/TTL 證據；若證據不是來自同一 commit/artifact，Gate 不成立。

### 4.5 PR、合併與紀錄

17. 一個 PR 不跨兩個 capabilities 的 data ownership；大型 capability 依「guardrail → contract → implementation → consumer migration → zero-use deletion」拆短 PR。
18. required checks 全綠、review 完成後才 merge main；刪除 branch，將 issue/PR/commit/artifact/evidence 回寫本文件與 Roadmap。
19. 任何後續 dependency change 若影響已通過證據，將該 Gate 標成 `EVIDENCE_STALE` 並依第 12 節重跑，不得沿用舊綠燈。

## 5. P2 — Kiosk Voice 與 Emotion Diagnostics

### 5.1 P2 目標

P2 同時修復 Kiosk 語音互動與重建 Admin 情緒分析。四個工作流必須在同一 P2 Gate 收斂，但 PR 可分開：

1. Voice 對話顯示順序。
2. 訪客入口與 stale artifacts 清理。
3. Silero VAD v5 菜單全程自動監聽。
4. Emotion Diagnostics 權威模型、UI、資料與 legacy purge。

### 5.2 P2.0 現況盤點與保護網

- 追蹤 Voice stream 的 `transcript/assistant_text/audio/done/error` 實際事件順序，固定 `voice_turn_id` 與 UI state transition。
- 盤點手動按鈕、RMS detector、passive keyword recorder、MediaRecorder、rolling buffer、camera capture、emotion inference 與 retry/cancel path。
- 盤點三種 emotion modes、Admin 頁面、settings、records、influence/effectiveness/human-evaluation APIs、tables、jobs 與 retention。
- 為現有觸控點餐、會員／訪客選擇、Voice playback failure、camera degradation 與 checkout 建立回歸基線。
- 產出 P2 legacy purge manifest；每個項目附 replacement、data class、刪除 migration 與 negative test。

### 5.3 P2.1 Voice Dialogue Display Order

權威契約：同一 Voice Turn 必須先建立 customer row，再顯示 assistant text。可用 partial transcript 時立即顯示；尚無文字時顯示「語音辨識中…」，final transcript 到達後原位替換。Assistant 音訊不等待 final transcript，避免增加 Voice Response Wait。

修改流程：

1. 將 stream event 歸一成單一 per-turn reducer/state machine，禁止各 callback 直接用完整 `innerHTML` 互相覆寫。
2. `transcript` 更新既有 customer row；`assistant_text` 只有在 customer row 已存在時才建立 assistant row；`done/error` 只能完成同一 turn。
3. 忽略舊 turn、取消 turn 或 retry 的 late events；同一 `voice_turn_id` 不得建立第二組 rows。
4. 保留 Progressive Voice Response：assistant text 可在驗證後立即顯示，TTS 可串流，但畫面順序不得反轉。

驗收：

- Assistant event 先到、transcript 後到時，畫面仍是 customer placeholder → assistant → final transcript 原位替換。
- Partial/final transcript、取消、重試、playback failure、late event 各有 unit test。
- E2E 以人工控制串流事件順序驗證 DOM order、ARIA live behavior 與不重複 row。
- Voice Response Wait 的既有 P95 目標不得因 UI ordering 增加音訊等待。

### 5.4 P2.2 訪客入口與建置殘留

保留點餐方式頁的獨立「直接點餐」訪客入口；只刪除舊「略過，直接點餐」按鈕、handler、selector、copy、test fixture 與 stale build/source-map 內容。

驗收：

- Source、production bundle、source map 與 rendered DOM 都不存在舊字串或舊 selector。
- 唯一訪客入口仍走 server-authoritative Guest Ordering Choice；失敗可見、可 retry，不可靜默進菜單。
- 會員登入、註冊、返回點餐方式與訪客點餐 E2E 全通過。
- 產物由支援的 frontend build 重新產生，不手改 `dist`。

### 5.5 P2.3 Silero VAD v5 自動語音模式

依 ADR-0055/0056 實作既有 domain contract：

- Silero VAD v5 ONNX、ONNX Runtime Web 與 AudioWorklet 必須由專案 version-pin 並隨應用提供，不用 CDN 或 `latest`。
- Menu Ready 到 Order Confirmation、取消、session timeout 或 Kiosk reset 期間自動監聽，不需 customer 按下 voice button。
- 採 Open Speech Activation；至少 250 ms speech、1.2 s ending silence、單 turn 最長 30 s。
- 接受 speech 後暫停監聽，經 STT、assistant、TTS/playback 後最多 500 ms echo cooldown 再恢復，禁止重疊 turn 與自收音。
- 顯示 listening、processing、playback、unavailable；VAD/worklet/permission 失敗時不退回 RMS 或手動 voice button，觸控點餐仍可用。
- Turn 開始後保留「立即送出」與「取消」作為 recovery，不把它們當 activation control。

修改流程：

1. 以一個 VAD adapter 包住模型資產與 lifecycle；移除第二套 RMS decision path。
2. 將 microphone、VAD、recorder、Voice Turn、TTS playback 與 echo cooldown 收斂成可測 state machine。
3. 移除 passive keyword recommendation recorder 及其 settings、events、timers 與 UI。
4. 將 model load/permission/runtime failure 映射成明確 unavailable，不讓 promise、recorder 或 audio track 遺留。
5. 加入資產 checksum/version test、offline load test、reload/restart test、長時間 memory/track cleanup test。

實機 Gate：在預定 Kiosk Chromium、麥克風、喇叭與門市背景音環境驗證安靜、單人語音、短噪音、多人背景談話、TTS echo、連續十個 turns、取消、斷網與權限拒絕；記錄 false activation、missed speech、end-of-speech latency 與資源釋放，不用主觀「感覺可用」代替證據。

### 5.6 P2.4 Admin Emotion Diagnostics 重構

保留且只保留下列權威功能：

- 選擇已安裝且相容的 Emotion Model Profile；預設 R1-Omni，不自動 fallback。
- Customer Emotion Analysis Mode：Off、Periodic Ordering、Voice Only 三選一。
- Periodic Emotion Clip Duration：2～30 秒、預設 5 秒。
- Periodic Ordering 從進入菜單開始，到 Order Confirmation、取消、session timeout 或 reset 結束；capture → inference → record 串行，不累積 backlog。
- Voice Only 只使用對齊同一 Voice Turn 的 audiovisual evidence；未驗證 audio-only 時明確 skip emotion，永不阻擋 Voice。
- Live Admin Emotion Test：一次性影音錄製、2～30 秒、預設 5 秒、自訂 Prompt、可還原 server default、顯示結構化分析結果。
- Emotion Analysis Record 只顯示與保存：時間、事件、模型、情緒、強度、表情、聲音、描述；store-scoped 保存 30 天。
- 情緒固定為 Neutral、Happy、Angry、Frustrated、Anxious、Confused、Undetermined；強度固定為 Low、Medium、High、Undetermined。
- Raw image/video/audio/transcript inference 後立即刪除；submitted inference 失敗仍寫一筆安全的 Undetermined record。
- Emotion 永遠是 advisory，不改回答、推薦、價格、campaign、cart 或 order。

永久刪除：舊 intervention/assistance modes、rollout/confidence gates、human evaluation、effectiveness evidence、voice influence、assistance outcomes，以及其 UI、API、code、tables 與既有資料。此項依 ADR-0057 **不備份且不可復原**；執行前必須用 purge manifest 精確列出目標，禁止以 wildcard 或廣泛目錄刪除。

修改順序：

1. 先固定 settings、readiness、analysis request/result、record 與 failure contracts。
2. 建立最小新 schema/forward migration 與 retention job，鎖定 store isolation、TTL 與 raw-media absence。
3. 讓 periodic、voice-only、live-test 三個 producer 寫入同一 record contract；設定與 runtime readiness 分離。
4. 重設 Admin information architecture：設定、即時影音測試、分析紀錄三區；移除舊 intervention/effectiveness surfaces。
5. 切斷 Voice/Recommendation 對情緒 intervention 的讀取與寫入。
6. 執行永久 purge migration；用 schema inspection、static search、route negative tests 與 empty legacy telemetry 驗證。

### 5.7 P2 Functional Acceptance 與 Pilot Admission

P2 Functional Acceptance 必須具備：

- 四個 P2 工作流的 domain/unit、HTTP contract、permission、failure、frontend consumer、retention/security tests。
- PostgreSQL migration upgrade、fresh install、restart、TTL/purge 與 submitted-failure evidence。
- Admin/Kiosk typecheck、unit、production build、Playwright；production bundle 不含舊入口與舊 emotion surfaces。
- Docker CPU 基線與需要的 AI/GPU stack smoke；VAD 與 audiovisual emotion 在目標硬體實測。
- P2 收斂清單：尚未達 Emotion/Voice Module Independence Gate 的項目，逐項連結 P6 owner、風險與最晚關閉 Gate。

P2 通過後執行 Local Pilot Admission。若任一既有 runtime、security、transaction、recovery 或 artifact gate 失敗，狀態維持 `NOT YET DECLARED`，先建立 corrective issue 並重驗；不得以 P2 tests 綠燈直接宣告 Pilot Ready，也不得先開始 P3。

## 6. P3 — Project Core Brain

### 6.1 產品範圍

- 從 Admin 功能設定移除「推薦表現目標」及其 consumer；先盤點它是純 UI 設定、analytics contract 或仍有 runtime writer，不能只藏欄位。
- 建立獨立 `project-analyst` sidecar，只有手動 analyze/reanalyze。
- 顯示目前 revision、工作區狀態、readiness、明確測試與架構/文件缺口；只保留最新成功報告。
- 進階功能可為非核心文件或功能產生 Project Change Proposal，但不能修改 active workspace、apply、commit、push 或開 PR。

### 6.2 安全與資料邊界

- 只讀 allowlist：tracked source/tests/docs/non-secret config、CodeGraph facts、Git status/diff、Docker/API readiness 與明確 allowlisted tests。
- 禁止 `.env`、secrets、credentials、home/external paths、customer/business data、raw media、Docker socket、任意 shell 與未列出的 network target。
- Sidecar 以 non-root、read-only root filesystem、cap-drop、resource/time bounds 與獨立 volume/input snapshot 執行。
- Codex、Claude、Grok profile 各自通過 version/auth/headless/read-only/JSON schema probe 才顯示 Ready；一次明確選一個，不 fallback。
- 成功 rescan 原子取代舊報告；失敗保留舊報告、標 stale，只保存安全 failure reason。

### 6.3 既有 scaffold 的處理順序

1. 稽核 `project_brain_routes.py`、`project_brain_service.py`、tests 與 Admin consumer 的實際 authority。
2. 固定 Admin-facing HTTP contract，但將 analysis executor、provider credentials 與 snapshot handling 移到 sidecar boundary。
3. 刪除 UI API process 中的直接 filesystem/shell/provider execution；UI API 只負責 authorization、request、status 與 report projection。
4. Proposal 在 disposable isolated worktree 產生，只可新增 `docs/proposals/` 或 `extensions/<name>/`；回傳 patch、summary、tests，過期或拒絕即永久清除。
5. 為 path traversal、symlink、secret pattern、oversized input、timeout、provider malformed output、failed replace 與 concurrent scan 建立負向測試。

### 6.4 P3 Gate

- Sidecar isolation、evidence allowlist、provider readiness、no-fallback、latest-report atomicity 全部有可失敗測試。
- Proposal 不能改 active workspace；以 before/after Git tree、process permissions 與 filesystem mount evidence 驗證。
- 「推薦表現目標」的 source、bundle、API/settings consumer 與 generated contract usage 歸零；若底層 analytics 仍屬 P5.2 authority，記入收斂清單而非誤刪。
- Docker Compose、OpenAPI/client、Admin UI、failure/restart tests 指向同一 artifact。

P3 Gate 通過並登錄剩餘收斂債後，才開始 P4。

## 7. P4 — Optimization Lab（reference-only）

### 7.1 產品與隔離

- 獨立 module/container，與 Project Analyst 分離；只接受手動、單店、單一 store-day 的 Daily Optimization Simulation。
- 只產生 `reference_only` report，無 apply/publish/update action，不能改 LLM、Prompt、RAG、settings、campaign、recommendation、push、檔案或 production data。
- Input 只可來自明確選定的 de-identified Voice Interaction Evidence、synthetic fixtures 或 sanitized Admin import；不得讀 project files、Git、Docker、raw media 或 production volumes。

### 7.2 Evidence、分析與報告

- Voice Interaction Evidence 保存 30 天：遮罩後 STT、完整 LLM answer、RAG hit、voice outcome/safe failure、retry/correction；不得含 raw audio、member/device/session/order/payment identity 或 individual emotion。
- Redaction 在 persistence 前執行；無法安全去識別的 evidence 直接丟棄。
- Run 開始時凍結 store timezone 的單日 evidence IDs；當日報告標 partial 並記 cutoff。
- Codex、Claude、Grok 只顯示 provider-native model/effort；每次一個 analyzer，失敗不 fallback。
- Finding 固定分類：RAG Knowledge Gap、Prompt Behavior、Model Capability、Product Pipeline、Insufficient Evidence。
- 一至兩筆相似 evidence 只能是 Observation Signal；三筆以上或 synthetic reproducibility 才可產生 Reference Guidance。
- 具體 Prompt/model/RAG guidance 先通過隔離的 offline acceptance；未通過只顯示 Unverified direction。
- 報告固定六段，保存 30 天，只引用 opaque evidence IDs，不複製 transcript/answer。

### 7.3 權限、外傳與 Gate

- Report summary 使用一般授權；展開 evidence 需要 `optimization.evidence.read` 與 15 分鐘 manager step-up，逐次寫入不含內容的 audit。
- 每個 provider 預設 `synthetic_only`；customer evidence 需 provider-specific authorization、automation credential、outbound disclosure、retention acceptance 與 per-run egress audit。
- API schema 必須不提供 mutation action；network policy、credentials、mounts 與 permission tests 證明無 production write path。
- 驗證 evidence/report TTL、expired reference、redaction、store isolation、frozen cutoff、no fallback、classification threshold 與 offline rejection。

P4 Gate 通過並登錄收斂債後，才開始 P5.1。

## 8. P5 — 非智慧能力模組收斂

P5 不再以「功能出現」驗收，而以 Module Independence Gate 驗收。每個 capability 必須完成 interface、HTTP contract、data authority、authorization、failure、tests、frontend callers、migration、observability 與 evidence 十項要求；一個 capability 未通過，不增加 `1/10` 計數。

### 8.1 P5.1 — Identity & Device Access；Operations & Configuration

先 Identity，後 Operations；兩者都通過才進 P5.2。

Identity & Device Access：

- 校正 `admin_*`、`device_*`、`devices`、`fleet_*` owner 與所有 writer/readers。
- 收斂 device principal、Admin access、session、RBAC、credential lifecycle 與 audit interface。
- 移除 global identity service/repository imports、legacy principal/scope 轉接與未量測 compatibility path。
- 鎖定 anonymous/device-authenticated operation、store scope、credential rotation/revocation、restart 與 failure-closed tests。

Operations & Configuration：

- 校正 `commercial_settings_versions`、`admin_audit_logs` 與 capability status/readiness authority。
- 以 Docker Pilot external config 取代 stale `config/profiles/local-pilot.env.example`，secret 只由 host-external private source 提供。
- 將 `UI_API/deploy/postgres` 的 runtime role/init/WAL/backup 能力移入 canonical `docker/`，證明 replacement 後才刪舊 Compose。
- 將 `learning_data/settings.json` 的正式設定移入 Operations authority，測試值移至 fixtures。
- Admin 既有 raw fetch 逐點改用 generated client，依操作時限與 failure UX 設 bounded request。
- 鎖定 Core readiness 與 Optional capability warm-up 分離、shared-infrastructure degradation、audit 與 operator recovery。

### 8.2 P5.2 — Member；Campaign & Promotion；Recommendation & Interaction Analytics

依序完成 Member → Campaign & Promotion → Recommendation & Interaction Analytics，讓後者只能依賴前者發布的 interfaces/read models。

Member：會員、consent、preference、history、member session 單一 owner；訪客點餐不能因 Member degraded 被阻斷。

Campaign & Promotion：Campaign lifecycle/version/publication、promotion rule、push copy 與 active projection 單一 owner；移除 legacy promotion parallel truth。

Recommendation & Interaction Analytics：recommendation decision/event、commercial touch、interaction、effectiveness/analytics 單一 owner；placeholder 不產生商業觸點，移除 UI/API 中已取消的「推薦表現目標」，但保留 Roadmap 定義的合法營運觀測。

每個 capability 均執行：writer inventory → typed contract → new authority → consumer migration → telemetry zero → legacy deletion → Gate evidence。禁止為趕進度把三者合成一個共享 repository 或巨型 PR。

### 8.3 P5.3 — Ordering & Checkout Transaction Deep Module

收斂 Ordering Entry、Session、Cart、Quote、Checkout Confirmation、Order 與 Payment Pending handoff：

- Server 是價格、availability revalidation、quote、confirmation 與 order identity 的唯一 authority。
- 保留 idempotency、Confirmation Outcome Unknown recovery、transactional outbox 與 manual-payment Pilot boundary。
- AI、browser total、Member/Campaign/Recommendation 或跨能力 SQL 不得直接寫 transaction state。
- 跨能力讀取只使用已發布 interface/snapshot；同一 confirmation transaction 明確列出 lock、retry、outbox 與 failure invariant。
- 對 duplicate submit、timeout after commit、stale quote、sold out、dependency degraded、restart、outbox retry 與 payment pending 建立 PostgreSQL integration/E2E。
- 舊 cart/checkout/order routes、services、repositories 於 consumer 與 telemetry 歸零後刪除。

Ordering 通過 Module Independence Gate 後才開始 P6。

## 9. P6 — Intelligent Capability 收斂

順序固定為 Knowledge/RAG → Voice Assistance → Emotion Diagnostics，因為 Voice 可能消費 RAG，而 Emotion 可能觀測 Voice。P2 已驗收的 customer behavior 在此視為凍結契約；P6 是 ownership、adapter、failure isolation 與 legacy closure，不得暗中重定義 P2 UX。

### 9.1 Knowledge/RAG

- 將 Knowledge lifecycle、publication attempts、published pointer、retrieval configuration/checks 與 index artifact owner 收斂到一個 capability。
- RAG worker 透過 durable job/outbox 與 capability ports 執行；UI API 不直接操作 index/runtime internals。
- Generated client 取代 raw routes；刪除 legacy review/import/readiness parallel contracts 與空 allowlists。
- 鎖定 store isolation、atomic publish、failed publish 保留舊版本、retry/restart、retention 與 provider degradation。

### 9.2 Voice Assistance

- 將 Voice Turn journal、STT/LLM/TTS orchestration、candidate set、order draft proposal、playback outcome 與 interaction evidence 收斂成單一 capability。
- Silero browser adapter 與 UI state machine 是 Kiosk consumer，不成為 backend data authority；P2 Voice Dialogue Display Order 與 automatic listening 保持不變。
- STT/LLM/TTS/NIM/Ollama 是 adapters；每個 timeout/readiness/degradation 明示，禁止 Optional Voice 阻斷 Core ordering。
- 移除 legacy `/api/ask*`、passive recorder、voice recommendation side writes、直接 repository imports 與未量測 compatibility path。
- 鎖定 replay idempotency、same-turn retry、no duplicate order draft、playback failure、camera degradation、P95 response wait 與 30-day de-identified evidence TTL。

### 9.3 Emotion Diagnostics

- 將 P2 的 model profile、readiness、mode、capture orchestration、live test、record/TTL 收斂成 Emotion capability interface/API/ports/adapters。
- R1-Omni 是 adapter，不是 capability；model failure 只使 Emotion degraded，不阻斷 UI API、Voice 或 Ordering。
- 證明 P2 legacy purge 後無 intervention/effectiveness/human-evaluation/voice-influence path 復活。
- Admin/Kiosk/generated client 全部切換，legacy routes 與 horizontal services/repositories 於 telemetry zero 後刪除。

三者通過 Module Independence Gate 後，`Business Capability Modules passed` 應為 `10/10`；若任何一項缺證據，仍保持實際通過數字並進入修復，不得先宣告。

## 10. P7 — Legacy Closure 與 Project Completion

P7 不新增產品能力，只完成零使用、刪除、同成品驗證與結案。

### 10.1 全域零使用盤點

- Admin/Kiosk source 的 raw frontend `fetch` 歸零；只允許 shared generated transport 內的實作。
- `/api/*` compatibility routes 的 static consumer 與 runtime telemetry 歸零。
- 跨 capability repository import、cross-module SQL/write、global service access 與 internal HTTP loopback 歸零。
- Legacy settings、tables/columns、jobs、fixtures、flags、route allowlists、import exceptions 與 generated artifacts 全部有 replacement 或明確刪除證據。

### 10.2 最終刪除

- 刪除 giant `v1_routes.py`，將仍合法的 composition 移至 capability API/bootstrap；不得把內容原封不動搬成另一個巨檔。
- 刪除已空的 horizontal `routes/services/repositories/modules` 路徑與臨時 architecture allowlists。
- 刪除已歸零的 compatibility routes、adapters、telemetry counters 與 migration-only code。
- 保留 migrations、ADR、必要 audit 與可追溯歷史；不因「清理」刪除 authoritative business data、secrets、PostgreSQL volumes 或 backups。

### 10.3 同一候選成品完整驗收

1. Main clean checkout 由 CI 建立 digest-pinned images，不在 Pilot host 重建。
2. Fresh install 與既有資料 upgrade 都到 migration head；執行 schema/data reconciliation。
3. Backend Python matrix、PostgreSQL/Redis integration、frontend unit/typecheck/build、OpenAPI drift、architecture、shell checks 全綠。
4. Admin/Kiosk 全流程 E2E：裝置驗證、會員/訪客、catalog、campaign/recommendation、touch/voice ordering、checkout、unknown outcome、manual payment handoff、RAG、emotion、P3、P4。
5. Docker restart、capability warm-up、shared-infrastructure degradation、backup/restore與 Pilot Recovery Objective 實測。
6. Kiosk 目標硬體執行 VAD/noisy-store、STT/LLM/TTS、camera degradation、emotion AV 與長時間操作測試。
7. Security/retention：permissions、store isolation、secret/path escape、provider egress、30-day TTL、raw-media absence、audit 與 destructive-purge negative tests。
8. 同 artifact 觀測 legacy telemetry 為零，所有十個 Module Independence evidence 有效。

### 10.4 Project Completion Gate

只有下列條件同時成立才可更新為完成：

```text
Local Pilot Readiness: DECLARED for the current artifact
Business Capability Modules passed: 10 / 10
Independent Product Frontends passed: 2 / 2
Legacy compatibility usage: ZERO
P2–P7 convergence debt: ZERO open blocking items
P7 full-candidate verification: PASSED
```

## 11. 資料遷移、retention 與刪除政策

先分類再處理：

| 資料類型 | 預設處理 | 必要證據 |
| --- | --- | --- |
| Authoritative business data | 不直接刪除；forward migration、reconciliation、backup/restore 或明確 forward-recovery | row count/checksum、owner、upgrade/fresh install、restore/repair |
| Derived/read model/index | 可重建後替換；先證明 canonical source 與 rebuild | rebuild、atomic swap、failure retains old result |
| Raw media/transcript | 依 contract inference 後即刪或不落地 | storage inspection、failure path、crash/restart cleanup |
| 30-day evidence/report | TTL permanent delete，含 derived index/reference/backup policy | clock-controlled purge、expired lookup、audit |
| Pre-P2 emotion legacy evidence | 依 ADR-0057 不備份永久刪除 | 精確 manifest、migration、negative schema/API/static tests |
| Secrets/credentials | 不進 settings/report/log/patch；由外部 private source 提供 | secret scan、response/log redaction、mount/env contract |
| Build/cache artifacts | 由支援工具重建，不手改 | clean build、bundle/source-map static checks |

任何 material deletion 都必須解析精確 target；不得使用 workspace root、home、廣泛 glob 或未驗證環境變數作為 recursive deletion 目標。

## 12. 測試與證據策略

### 12.1 階段內測試層級

每個工作包至少覆蓋：

- Domain/unit：狀態、invariant、enum、boundary、idempotency。
- Interface/contract：typed interface、HTTP DTO/error/operation ID、OpenAPI/generated client。
- Adapter/integration：PostgreSQL、Redis/outbox/job、filesystem/object/index、provider adapter。
- Authorization/security：principal、permission、store scope、secret/path/network boundary。
- Failure/degradation：timeout、unready、restart、partial dependency、retry、no fallback。
- Consumer：Admin/Kiosk unit、DOM/ARIA、generated client、negative static checks。
- Runtime：Docker Compose、migration、health/readiness、smoke、resource cleanup。
- Retention：raw absence、TTL、purge、expired reference、audit。

### 12.2 影響式回歸

P3～P6 每次 merge 依 impact map 重跑 Pilot evidence：

| 變更 | 必重跑 |
| --- | --- |
| Identity/permission/device | Admin＋Kiosk admission、store scope、all protected operations |
| Schema/repository/migration | upgrade/fresh install、reconciliation、restart、backup/restore affected path |
| OpenAPI/client/frontend | contract drift、affected product unit/build/E2E、raw-fetch checks |
| Ordering transaction | catalog→cart→quote→confirm→unknown outcome→payment handoff |
| Voice/VAD/STT/LLM/TTS | browser model load、target hardware、audio lifecycle、response/playback failure |
| Emotion/camera/retention | AV permission/degradation、raw deletion、record/TTL、Voice non-blocking |
| Docker/config/readiness | config validation、startup/restart、warm-up、health、degradation |
| P3/P4 provider/evidence | isolation、no fallback、egress/audit、retention、no production mutation |

P7 不採抽樣，完整重跑第 10.3 節；證據必須屬於同一 commit、image digests、config fingerprint、migration head 與 target environment。

## 13. GitHub Issue、PR 與分支流程

```text
P-stage parent issue
  → capability/work-package child issue
  → acceptance criteria + evidence slots + convergence-debt link
  → short-lived branch
  → focused PR + required checks
  → merge main + delete branch
  → update evidence ledger and Roadmap
```

- 使用 `needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix` 五個預設 triage labels。
- 缺少 domain/data authority/acceptance decision 的 issue 保持 `needs-info`；只有可獨立驗收才標 `ready-for-agent`。
- 需要實機、credential、provider authorization、manager step-up 或 destructive review 時標 `ready-for-human`，不得由 agent 假設完成。
- Parent issue 不等於 monster PR；每個 child issue 有自己的 failure-first tests 與 evidence slots。
- PR description 必須列：scope/non-scope、authority before/after、migration、legacy replacement、tests、rollback/forward recovery、Roadmap/CONTEXT/ADR changes。
- Legacy deletion PR 必須能指向 replacement PR、consumer-zero evidence 與最後可回復 artifact。

## 14. 收斂債與完成度紀錄

P2～P4 採 Product Batch Functional Acceptance；可進下一批不等於 Module Independence。每次轉移前必須建立收斂清單，未登錄不得前進。

### 14.1 收斂債欄位

| 欄位 | 說明 |
| --- | --- |
| ID | GitHub issue 或穩定識別 |
| Origin | P2、P3 或 P4 的來源工作 |
| Affected capability | 最終 owner；無則標 non-core sidecar/module |
| Remaining gap | contract/data/consumer/legacy/test/observability/retention |
| Risk | 會造成的錯誤或重工，不用主觀百分比 |
| Required evidence | 可關閉該項的具體證據 |
| Latest closure gate | P5.x、P6 或 P7；不可無限延期 |
| Status | NOT_STARTED、IN_PROGRESS、BLOCKED、EVIDENCE_STALE、PASSED |

### 14.2 階段證據表

| Stage/Gate | 初始狀態 | 前置條件 | 完成時必填 |
| --- | --- | --- | --- |
| P2 Functional Acceptance | REPOSITORY WORK MERGED；hardware pending | Batch R complete | PR #40～#43、candidate evidence、target hardware |
| Local Pilot Admission | READY_FOR_HUMAN — NOT DECLARED | Target-device/security admission | new artifact、config fingerprint、full gate evidence、sign-off |
| P3 Functional Acceptance | WAITING LOCAL PILOT | Pilot declared | sidecar/proposal/security/provider evidence |
| P4 Functional Acceptance | WAITING P3 | P3 passed | isolation/evidence/report/egress/TTL evidence |
| P5.1 | WAITING P4 | P4 passed | two Module Independence Gate evidence sets |
| P5.2 | WAITING P5.1 | P5.1 passed | three Module Independence Gate evidence sets |
| P5.3 | WAITING P5.2 | P5.2 passed | Ordering Module Independence Gate evidence |
| P6 | WAITING P5.3 | P5.3 passed | RAG、Voice、Emotion Gate evidence |
| P7 Project Completion | WAITING P6 | 10/10 candidate | full-candidate evidence、legacy zero、debt zero |

完成度只以 Gate 狀態、issue/PR、commit/artifact、測試與阻塞項表示；禁止填寫主觀百分比。若證據受後續改動影響，狀態改為 `EVIDENCE_STALE`，不是保留 `PASSED` 加註備註。

## 15. 主要風險與控制

| 風險 | 控制 |
| --- | --- |
| 把既有 scaffold 當完成 | as-is classification、failure-first tests、Gate 十項證據 |
| P2 功能完成被誤報 10/10 | Product Batch Functional Acceptance 與 Module Independence 分開記錄 |
| Stale dist/source map 讓已刪 UI 復活 | clean build、bundle/source-map static gate、E2E DOM negative test |
| VAD 背景誤觸或 TTS 自收音 | noisy-store實機矩陣、half-duplex、echo cooldown、連續 turn soak |
| Emotion 重構仍留下第二套意義 | 精確 purge manifest、migration、API/schema/static negative tests |
| P3 洩漏 secret 或直接改 repo | read-only sidecar、allowlist snapshot、no socket/shell、isolated proposal worktree |
| P4 外傳 customer evidence | synthetic-only default、provider-specific authorization、egress audit、pre-persist redaction |
| P5 成為跨能力 monster PR | P5.1～P5.3 gates、每 capability 短 PR、禁止跨 owner |
| P6 重構破壞 P2 UX | 將 P2 customer behavior 作為 frozen consumer contract，影響式回歸 |
| 舊證據被後續修改失效 | artifact identity、impact map、`EVIDENCE_STALE`、P7 full rerun |
| Legacy 過早刪除 | replacement → migration → zero use → deletion 固定順序 |

## 16. 前進、停止與例外規則

- 前一 Gate 未通過，不開始下一 P 階段；不得以平行工作隱藏未完成 authority。
- P2～P4 功能通過但有架構缺口時，只能在收斂清單完整登錄後前進；資料安全、核心交易、Pilot admission 或 security blocker 不得延期。
- Provider/model 不 Ready 時明確失敗，不自動換 provider/model/effort。
- Optional AI capability 失效不得阻斷 Core ordering；Core invariant 無法保護時 fail closed。
- 實作發現 domain/data authority 與本計畫不符時先停該工作包，更新 issue、CONTEXT/ADR/plan 後再繼續，不在程式中偷偷做新決策。
- 任何 destructive target 不精確、migration 無 recovery、customer evidence 未授權、實機條件未提供時停止並標 `ready-for-human`。
- P7 通過前不得宣告 Project Completion；P7 通過後仍不代表 production HA 或本計畫外能力完成。

## 17. 當前交接點

P2 repository implementation 已由 PR #40～#43 合併；本文件保留原始設計。新的執行 Codex 不重做 P2，應依 [Remaining Work Handoff](Project_2026_Remaining_Work_Execution_Handoff.md) 從 Local Pilot target-device/security admission 開始，通過後依序完成 P3～P7。

## 18. 決策索引

P2 Emotion：[ADR-0027](docs/adr/0027-select-only-installed-compatible-emotion-model-profiles.md)、[0028](docs/adr/0028-keep-customer-emotion-analysis-advisory-only.md)、[0029](docs/adr/0029-skip-unvalidated-audio-only-emotion-without-blocking-voice.md)、[0030](docs/adr/0030-stop-periodic-emotion-capture-at-the-ordering-boundary.md)、[0031](docs/adr/0031-retain-only-minimal-emotion-analysis-records-for-thirty-days.md)、[0032](docs/adr/0032-normalize-emotion-and-intensity-at-the-api-boundary.md)、[0033](docs/adr/0033-record-submitted-emotion-inference-failures-safely.md)、[0057](docs/adr/0057-permanently-remove-legacy-emotion-intervention-evidence.md)、[0059](docs/adr/0059-separate-emotion-configuration-from-runtime-readiness.md)。

P2 Voice：[ADR-0007](docs/adr/0007-deepen-voice-turn-orchestration.md)、[0025](docs/adr/0025-require-synthesized-speech-output-for-a-successful-voice-turn.md)、[0055](docs/adr/0055-pin-browser-vad-to-silero-v5.md)、[0056](docs/adr/0056-adopt-menu-wide-open-speech-voice-listening.md)、[0060](docs/adr/0060-warm-capabilities-beside-the-service-not-in-front-of-it.md)。

P3：[ADR-0034](docs/adr/0034-bound-the-project-core-brain-to-read-only-evidence.md)～[0040](docs/adr/0040-confine-non-core-proposals-to-new-isolated-modules.md)。

P4：[ADR-0041](docs/adr/0041-test-daily-optimization-without-production-mutation.md)～[0052](docs/adr/0052-require-provider-specific-authorization-for-customer-evidence.md)。

P5～P7 架構：[ADR-0021](docs/adr/0021-adopt-docker-first-immutable-pilot-delivery.md)、[0022](docs/adr/0022-preserve-ordering-during-shared-infrastructure-degradation.md)、[0023](docs/adr/0023-organize-the-application-by-business-capability-contracts.md)、[0024](docs/adr/0024-separate-admin-and-kiosk-product-frontends.md)。
