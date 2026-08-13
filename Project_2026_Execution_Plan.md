# Project_2026 執行計畫與完成狀態

> **狀態基線**：`main@9ac0a1c`，2026-08-12
> **本文件是唯一的流程權威**。它取代並合併了先前的四份文件：`Project_2026_P2_to_P7_Execution_Plan.md`、`Project_2026_Project_Completeness_Roadmap.md`、`Project_2026_Remaining_Work_Execution_Handoff.md`、`Project_2026_Remaining_Work_Codex_Prompt.md`。
> **領域詞彙**以 [`CONTEXT.md`](CONTEXT.md) 為準，**決策**以 [`docs/adr/`](docs/adr/) 為準，兩者不受本文件取代。
> **本文件是「狀態」的權威**：現在通過了什麼、證據在哪、缺什麼輸入。
> **[`docs/upgrade/`](docs/upgrade/) 是「路線」的權威**：要成為 Commercial V1 還要做什麼、順序與 Gate。
> 兩者對「已達成什麼」若有出入，以本文件為準並修正路線文件。

---

## 1. 文件責任

本文件回答三個問題，且只回答這三個：

1. **現在的嚴格完成狀態是什麼**（第 2 節）
2. **已經完成了什麼、證據在哪裡**（第 3 節）
3. **還沒完成什麼、缺什麼才能繼續**（第 4、5 節）

規則：

- 不使用主觀完成百分比。
- 「有檔案／有 route／有 Issue／有測試」不等於完成。只有通過 Gate 並留下同 artifact 證據才算。
- 「PR merged」不等於「該 Issue 全部 scope 通過」。
- 若本文件與 Git、GitHub、CI 或實測證據衝突，以後者為準，並在下一個文件 PR 修正本文件。

---

## 2. 嚴格完成狀態

```text
Local Pilot Readiness:            BLOCKED — NOT DECLARED
Business Capability Modules:      1 / 10 passed
Independent Product Frontends:    2 / 2 passed
Project Core Brain (P3):          REPOSITORY SCOPE PASSED；provider 執行 ready-for-human
Current active stage:             P4→P7 repository convergence（local Ollama；外部/hardware evidence blocked）
Legacy HTTP compatibility surface: ZERO（2026-08-12 撤除 67 條，見 ADR-0062）
Legacy horizontal layer usage:    capability interface 已全部不讀 services／repositories（10/10）
                                  共用基礎設施仍在 services／repositories，屬跨能力依賴
Project Completion:               NOT ACHIEVED
```

| 階段 | 狀態 | 前置／阻塞 |
| --- | --- | --- |
| P0 Kiosk 關鍵路徑 | PASSED | — |
| P1 Admin operations 與 retained RAG | PASSED | — |
| Batch R 重啟可用性與裝置驗證 | PASSED | — |
| Catalog & Availability Module Independence | PASSED（1/10） | — |
| P2 Kiosk Voice＋Emotion Diagnostics | Repository 實作已合併；實機證據未取得 | 目標 Kiosk |
| **Local Pilot Admission** | **BLOCKED — NOT DECLARED** | Pilot Configuration Authority＋目標實機（兩者皆缺） |
| P3 Project Core Brain | Repository scope PASSED；外部 CLI deferred by owner | Codex／Claude／Grok CLI 與自動化憑證（不實作） |
| P4 Optimization Lab | REPOSITORY PATH PASSED（local Ollama）；customer-evidence path deferred | customer-evidence authorization／encrypted-at-rest deployment evidence |
| P5.1 Identity／Operations | REPOSITORY CONVERGENCE EVIDENCED；external gate open | Pilot authority／PostgreSQL production／auth evidence仍待外部 |
| P5.2 Member／Campaign／Recommendation | REPOSITORY CONVERGENCE EVIDENCED；external gate open | consumer evidence仍待逐項收斂 |
| P5.3 Ordering & Checkout | REPOSITORY CONVERGENCE EVIDENCED；external gate open | 完整觸控語音 E2E、confirmation restart 與 Pilot evidence仍待逐項收斂；outbox/retry/dead-letter、cart revision concurrency 已有 repository evidence |
| P6 Knowledge/RAG → Voice → Emotion | REPOSITORY CONVERGENCE EVIDENCED；external gate open | provider／hardware／retention evidence仍待逐項收斂 |
| P7 Legacy Closure | STATIC/LOCAL CANDIDATE EVIDENCED；closure gate open | HTTP compatibility removal 已完成；horizontal 層收斂與外部成品矩陣仍未通過 |

### 2.1 已記錄的順序例外

原本的固定順序把 P3～P7 全部排在 Local Pilot Admission 之後。**2026-08-11 專案擁有者決定**：移除所有 pilot 登入憑證、目前不建立任何登入認證，並暫停 Local Pilot、先進行架構收斂。

這是**被記錄的例外，不是通過的 Gate**。後續不得以「已進入 P3／P4」推論 Local Pilot 已成立。

恢復 Local Pilot 的重新進入條件見第 4.1 節。

---

## 3. 已完成的工作

### 3.1 P0～Batch R（本輪之前）

| 交付 | Issue | PR | Merge commit |
| --- | --- | --- | --- |
| P0 Kiosk 關鍵路徑修復 | — | #9 | `09c018d` |
| P1 Admin operations 與 retained RAG | #10 | #13 | `887f965` |
| Batch R 重啟可用性與裝置驗證 | #11 | #16 | `767e509` |
| Catalog Module Independence Gate | #12 | #15 | `3dd51f4` |
| Catalog 子項 | #1～#8 | — | 全部關閉 |

Catalog & Availability 是目前唯一通過 Module Independence Gate 的 Business Capability Module。

### 3.2 P2 Kiosk Voice＋Emotion Diagnostics — repository 實作

| PR | Merge commit | 內容 |
| --- | --- | --- |
| #40 | `d069068` | Voice Dialogue reducer 與 Emotion contract |
| #41 | `371c5a7` | Pilot AI Compose endpoint/mode alignment |
| #42 | `f5967a6` | 刪除 passive voice recorder legacy |
| #43 | `00132a5` | 記錄 repository/host Local Pilot evidence |

已關閉的子項與證據：

- **#21 Voice dialogue reducer** — `UI_API/frontend/kiosk/voiceDialogueReducer.js` 與紅燈優先的 `voice-dialogue-reducer.test.ts`。顧客列先於 assistant 文字、partial/final 原位替換、stale/duplicate/cancelled 事件忽略，全部是 reducer 層可證。
- **#22 Guest 入口與 stale artifact** — `guestOrdering.js` 為唯一權威，未接線的呼叫端以 `guest_ordering_choice_unwired` 明顯失敗；`tools/demo_passive_voice.py`（657 行）已刪除並有零使用負向測試。
- **#24 Emotion 契約與 ADR-0057 purge** — 三個 canonical mode 為唯一權威，legacy mode 值被拒，`EMOTION_ENABLED` 一次性前向遷移後移除，purge manifest 為精確四項且有安全邊界。

**仍未關閉**：

- **#19 P2 parent**（`ready-for-human`）— P2 Functional Acceptance 未成立。
- **#23 Silero VAD v5**（`ready-for-human`）— repository scope 完成（Silero 為唯一支援偵測器、無 RMS/手動 fallback、失效可見且觸控點餐仍可用）；250 ms／1.2 s／30 s／cooldown／noisy-store 驗收需實體 Kiosk。

### 3.3 R0 進度治理修正

**PR #45**（`b6fa0b4`）。查證結果：

| 驗證項 | 結果 |
| --- | --- |
| `d069068`／`371c5a7`／`f5967a6`／`00132a5` | 四者皆為 `main` 祖先 |
| PR #40～#43 | 全部 MERGED，merge commit 對應上列四者 |
| CI run `31490505354` | 六個 required checks 全 success |
| P3～P7 新 commits／PRs／Gate evidence | 無 |

修正內容：#21／#22／#24 附逐項證據關閉；#23／#19 改 `ready-for-human`；Roadmap 與舊 Plan 的「P2 NOT_STARTED」修正；新建 #44 追蹤 Pilot 容器安全缺口。

### 3.4 G0.1 Pilot 容器安全硬化

**Issue #44 · PR #46**（`2d9ff98`）· [ADR-0061](docs/adr/0061-run-the-pilot-on-a-read-only-container-contract.md)

先前的 Local Pilot 跑在開發 stack 上：`APP_ENV=development`、`SECURITY_ENFORCED=false`、diagnostic routes 開啟、root filesystem 可寫、完整 Linux capability set。

`docker/compose.pilot.yaml` 現在是 Pilot runtime 契約：`migrate`／`app`／`worker` 套用 `read_only: true`、`cap_drop: [ALL]`、`no-new-privileges:true`、non-root uid 10001，只保留 `/tmp` 一個 `nosuid,nodev` tmpfs。設定與 secrets 來自三個 `${VAR:?}` 主機外部檔案，缺任一個就在 `docker compose config` 階段失敗。

**結構性 gate**：`UI_API/tests/test_pilot_container_security.py`，27 tests，突變驗證過（翻轉 `read_only`、加回 `NET_RAW`、替換 `no-new-privileges`、`user: "0:0"`、把 secret 從 `${VAR:?}` 降級為 `${VAR}`，每一項都被擋下）。

**執行期證據**：`docker/scripts/verify-pilot-security.sh` 22/22 通過——`CapPrm`／`CapEff`／`CapBnd` 全為零、`NoNewPrivs: 1`、rootfs 寫入全部 `EROFS(30)`、allowlist 路徑可寫、secrets 0600 可讀但不進環境變數與 log、diagnostic/demo/debug routes 404。

**過程中發現的兩件事**：

1. **先前記錄的 Pilot 證據是用 compose 預設憑證取得的**。資料庫角色密碼是字面值 `project-2026-local`，不是 repository `.env` 的值——那組 stack 是在沒帶 `--env-file .env` 的情況下啟動的。任何有帶的呼叫都會認證失敗。
2. **出貨的 Pilot profile 無法啟動**。`config/profiles/local-pilot.env.example` 宣告 `DATABASE_RUNTIME_ROLE=project_runtime`，migration 會授權它但不會建立它，第一次 migration 直接失敗。`docker/scripts/provision-pilot-database-role.sh` 以 idempotent 方式建立。

### 3.5 G0.2 候選成品驗證

**PR #50**（`8c4cf45`）。完整證據見 [`docs/agents/p2-local-pilot-readiness.md`](docs/agents/p2-local-pilot-readiness.md)。

候選成品 `2d9ff98`（image 內原始碼與工作樹逐檔 md5 相符）：

| 項目 | 值 |
| --- | --- |
| app／worker | `project-2026:ai@sha256:8d9d7b62…` |
| 核心 runtime | `project-2026:local@sha256:728adc6e…` |
| R1-Omni | `project-2026-r1-omni:gpu@sha256:e80c34e7…` |
| PostgreSQL | `postgres@sha256:1961f96e…` |
| Ollama | `ollama/ollama@sha256:4dea9fb5…` |
| merged compose fingerprint | `b66bd2e3aa6fa892…` |
| migration head | `0027_remove_pre_pilot_rag_history`，27 applied，0 pending |

通過的檢查：

- **容器安全** 22/22。
- **Backup/restore 對帳**：1,523,010 bytes custom-format dump 還原到具名暫存資料庫；兩邊皆 27 migration rows、74 tables；`md5(string_agg(version||':'||checksum))` 相同為 `cce1174a…`；暫存資料庫與 dump 精確移除後 `pg_database` 計數為 0。
- **重啟與 warm-up**：停機時 `HTTP 000`（量測有真實零點），啟動後 Core `/ready` 於 **2611 ms** 回 200，當下 `stt` 與 `rag` 仍在 `pending`／`warming`——符合 ADR-0060。
- **Migration 重跑** idempotent；adapter coverage 19/19；Edge TTS 合成 15,840 bytes。
- **`docker/scripts/test.sh`** 158 passed＋Docker smoke passed。
- **`docker/scripts/test-ai.sh`** 三項探測全 PASS。
- **前端** typecheck／syntax／build 通過；coverage 92.97% statements、80.36% branches。

**兩項對舊證據的修正**：

1. 舊 `f5967a6` 記錄標為 `EVIDENCE_STALE`，並載明它是用 compose 預設憑證認證的。
2. 舊記錄的 Playwright 證據是在 `SECURITY_ENFORCED=false` 下取得的。在 Pilot profile 下，五個測試有四個連菜單都到不了——被 Kiosk 裝置驗證對話框擋住。**這是 fail-closed 的正確行為**，代表 Pilot profile 下的瀏覽器證據需要裝置憑證發放，屬實機範圍（#20／#23），未以開發設定的結果代替。

### 3.6 P3 Project Core Brain — repository scope

**Issue #26 · PR #51／#52／#53／#54／#55**

| 片段 | PR | Commit | 測試 |
| --- | --- | --- | --- |
| 證據 allowlist | #51 | `d32e46f` | 71，18 個突變全數擋下 |
| 隔離 sidecar | #52 | `66a8232` | 35 |
| 接線並刪除 in-process 路徑 | #53 | `8c86b47` | 26 |
| 提案工作流 | #54 | `74a509f` | 36，零跳過 |
| Gate 收尾（歷史基線） | #55 | `80347a8` | 全套 325 passed |

**證據 allowlist**（[ADR-0034](docs/adr/0034-bound-the-project-core-brain-to-read-only-evidence.md)）：`UI_API/backend/project_analysis/evidence.py` 是所有專案分析讀取的唯一入口。採 allowlist 而非 denylist——denylist 回答的是「這是不是我想到的壞路徑」，一旦有人新增目錄就不再成立。拒絕理由只給規則名稱，不給解析後的主機路徑，所以拒絕本身不能用來探測檔案系統。18 個突變（每個 `raise _reject(...)` 改成 `pass`、每個憑證字串片段停用、把 runtime 目錄加進 allowlist）全部被測試擋下。

**隔離 sidecar**（[ADR-0036](docs/adr/0036-run-project-analysis-in-a-dedicated-sidecar.md)）：獨立服務、獨立 image、獨立 uid 10002。在跑著的容器上實測：**零掛載**（`docker inspect .Mounts` 為空）、`CapEff`／`CapBnd` 全為零、`NoNewPrivs: 1`、`/tmp` 外全部 `EROFS(30)`、無 `/var/run/docker.sock`、`/repo`／`/app`／`/var/lib/project-2026` 皆不存在、`pids_limit=256`、`mem_limit=2g`、不對主機發布 port。

**無 fallback**（[ADR-0037](docs/adr/0037-select-only-ready-project-analyst-profiles.md)）：無憑證時三個 profile 全報 `cli_not_installed`，`/analyze` 回 409，且測試斷言 provider 呼叫清單為**空**——不是「回了錯誤」，是「沒碰到任何 provider，包括替代品」。

**sidecar 不採信呼叫端**：它重新驗證每一個 evidence 路徑。實測 `../../etc/passwd`、`UI_API/.env`、`/etc/shadow` 都被 sidecar 自己以 422 擋下。

**provider 回應不救**：散文、schema 不符、未知 severity、引用未提供的檔案，全部整筆拒絕。

**報告原子性**（[ADR-0038](docs/adr/0038-retain-only-the-latest-project-analysis-report.md)）：成功 rescan 以 `os.replace` 原子替換且舊報告消失；失敗 rescan **保留**舊報告並標 `stale` 加有界理由——後者更重要，因為看起來仍是最新的舊報告是沒人會去查時間戳的那種失敗。

**提案工作流**（[ADR-0039](docs/adr/0039-generate-project-change-proposals-without-applying-them.md)、[ADR-0040](docs/adr/0040-confine-non-core-proposals-to-new-isolated-modules.md)）：用 clone 而非 `git worktree`——`git worktree add` 會寫 metadata 進來源的 `.git`，clone 只讀來源、不寫回，這讓「不能修改工作區」成為**掛載的性質**而不是程式碼裡的承諾。隔離目錄只在單一請求期間存在並在 `finally` 移除，使「拒絕或過期須永久移除隔離 worktree 與產物」由結構成立，而不是另一條有人得記得跑的清理路徑。測試對**真實 git repository** 斷言來源樹逐位元組相同，`HEAD`、分支、`git log`、`git status --porcelain` 全部不變。

**legacy 歸零**：UI API 進程已無 `llm_gateway_service`、`subprocess`、shell（以 AST 驗證，不是抓字串——抓字串會被「解釋為何不存在」的 docstring 誤中）。in-process 提案產生器已刪除。

**收斂債清除**：`RECOMMENDATION_TARGET_EFFECTIVE_FROM` 仍在持久化的 settings 文件裡。契約拒絕它、公開投影排除它，所以 P1 的退役測試一直是綠的，而 `load_settings` 仍把它併進每個內部呼叫端看到的內容。已移除並加上會擋的測試。

**過程中的三個發現**：

1. **執行期 shell 拿 git 版本永遠回 `unknown`**——runtime image 沒有 git 也沒有 repository。改為 `APP_GIT_REVISION` build argument（對 digest-pinned 成品而言版本本來就是 image 的性質），實測烘入 `8c86b47` 且 snapshot 正確讀到。
2. **`git clone --shared=false` 不是合法參數**（`--shared` 不吃值），而 refusal code 把 git 的錯誤吞掉，導致它一路靜默失敗。
3. **13 個測試在 image 沒有 git 時會 skip**——而會 skip 的正是證明隔離的那些。測試 image 現在裝 git，skip guard 已刪除。另外 symlink 測試原本會在原始碼樹裡種 symlink，已改為在暫存目錄建假的 repository root；整套既有測試在**唯讀掛載**上跑完 356 passed（Python 3.10；Python 3.12 baseline 355 passed），新增的 Dockerfile context regression 亦通過，這才真的證明沒有測試會寫入原始碼樹。

### 3.7 P4 Optimization Lab — repository foundation

**Issue #30** 已完成不依賴外部憑證的 repository foundation，但不宣告完整 P4 Gate。`UI_API/backend/modules/optimization_lab/` 現在提供：

- 明確的 synthetic-only 與 local Ollama analyzer profile；Codex／Claude／Grok profile 在 owner deferred 狀態顯示 not-ready，不能 fallback。
- store-scoped de-identified Voice Interaction Evidence；輸入拒絕 raw media、identity、session、order、payment 與 individual emotion 欄位，已知 email／phone／長數字先遮罩。
- 以門市 timezone 凍結單店單日 snapshot；當日標 `partial`，snapshot evidence IDs 不會被後續事件改寫。
- 固定六段 Daily Optimization Reference Report；報告只保存 opaque evidence IDs、分類、計數與離線驗收狀態，不複製 STT／LLM 內容。
- Observation Signal／Reference Guidance／Insufficient Evidence 門檻、固定五類 finding classification、provider model／effort validation、customer-evidence authorization fail-closed、step-up evidence expansion audit 與 30 天清除。
- SQLite test adapter 與 PostgreSQL migration `0028_optimization_lab.sql`（並已登記至 capability registry）；Admin summary／synthetic fixture／simulation／report routes 已接入既有 device-auth Admin boundary；local Ollama 只使用 `LOCAL_ONLY` gateway policy。

Repository evidence：`UI_API/tests/test_optimization_lab.py`、`UI_API/tests/test_optimization_migration.py`、`UI_API/tests/test_dockerfile_layering.py`、capability independence tests；本次 P4/Docker/capability focused tests **18 passed**，完整 backend suite **356 passed**（285 app + 71 isolated sidecar/proposal），Python 3.12 baseline suite **355 passed**，candidate Ruff check／format 亦通過，capability／optimization module mypy **44 files** passed。Current candidate image 在 temporary PostgreSQL fresh/reapply 均為 **28 applied / 0 pending**、無 checksum mismatch，PostgreSQL adapter/schema/status **8 passed**，live Redis shared integration **9 passed**；最終 static/security focused suite **54 passed**（含 Dockerfile-specific ignore/docs-copy regression），exact-candidate Playwright **5 passed**；PostgreSQL-backed exact runtime 在重啟前後 `/live`／`/ready` 均為 200，20/20 adapters covered，migration head `0028`；暫存資料庫、Redis、runtime container 均已清除。Ollama `qwen3.5:4b` 的 host-local probe 實際回傳四個允許 metric objects，`LLMModelPolicy.LOCAL_ONLY` 成功；echo／unknown top-level schema 則被拒絕且不 fallback。Candidate image digests 已記於 [`docs/agents/p4-p7-final-verification-matrix.md`](docs/agents/p4-p7-final-verification-matrix.md)。

**仍未完成，且不能由 repository 偽造**：customer-evidence provider authorization／retention review、加密 at rest 與 provider egress deployment evidence，以及同候選成品的 P4 network/mount proof。Codex／Claude／Grok CLI 依 owner 決定暫不實作；local Ollama failure 會 fail closed 且不 fallback。P4 local repository path 完成前，後續 P5→P7 只推進不依賴上述輸入的 repository work。

### 3.8 獨立 repository fixes

- **Issue #47 `/docs`**：採較小暴露面的 Option 1；`APP_ENV` 為 staging／pilot／production 時關閉 `/docs`、`/redoc`、`/openapi.json`，development／test 保留。`docker/scripts/verify-pilot-security.sh` 已將三者納入 404 probe，並有正向／負向測試。
- **Issue #48 Dockerfile layer**：`base`／`application`／`runtime` 與 source-free `ai-base` 分離；AI dependency install 發生在 `COPY UI_API/` 前，runtime target 置於 AI stage 前以避免 legacy builder 為 CPU runtime 安裝 AI stack。兩次完整 AI candidate build 已完成；第二次只改 `UI_API/` source 時，`requirements-ai.txt` COPY 與 pip install 層均維持 `CACHED`，只有 source/application layer 重建。

### 3.9 P4→P7 repository convergence — local-only path

依專案擁有者決定，Codex／Claude／Grok CLI、其自動化憑證與 customer-evidence 授權暫不實作；P4 analyzer 現以既有 Ollama gateway 的 `LOCAL_ONLY` policy 為唯一非合成路徑。Ollama timeout、schema failure 或 unavailable model 會回傳明確錯誤，不會 fallback 到 synthetic 或 cloud provider。

目前已建立十個 manifest capability 的 published `contracts.py`／`interface.py` package，另有獨立的 P4 Optimization Lab surface；並將 Ordering、Campaign／Promotion、Recommendation／Analytics、Knowledge／RAG、Voice、Emotion、Member、Identity、Operations 的既有 route/application 入口改由 capability surface 進入。Admin／Kiosk feature code 的瀏覽器 transport 已集中到 `frontend/shared/api/capabilityClients.js` 與 shared transport，feature files 不再直接組裝 `/api/v1` URL 或呼叫 `fetch`。

Repository evidence：capability boundary tests、P4 local analyzer tests、backend suite **356 passed**（唯讀 source mount、`-p no:cacheprovider` 亦通過）、Python 3.12 baseline suite **355 passed**、temporary PostgreSQL adapter/schema/status run **8 passed**、candidate Redis shared integration **9 passed**、frontend syntax/typecheck/build 及 **130 frontend tests passed**（93.18% statements／80.57% branches／94.91% functions／93.30% lines）。Identity、Operations、Recommendation route adapters now resolve through published capability interfaces；production routes have an explicit legacy-import allowlist limited to development routes and the deferred Project Analyst sidecar；所有 route module 已通過 `modules.*`／`repositories.*` horizontal import zero-use gate；Admin/Kiosk feature transport 已通過 shared capability client 與 raw `fetch` 邊界檢查，診斷、session/log、push-copy、Project Analyst 與 Kiosk facade 亦已切換到 versioned client seam；Member Admin detail／verified preferences／delete／CSV export 已切換到 canonical `/api/v1/members` surface；巨型 `v1_routes.py` 已拆除為 capability-owned compatibility modules；candidate OpenAPI publishes 101 `/api/v1` paths 與 0 條未版本化 `/api/*`，generated catalog contract matches；Ollama schema gate 以 fail-closed 測試固定；PostgreSQL-backed exact runtime 在重啟前後均回報 `/live`、`/ready`，20/20 adapters covered，migration head `0028`；exact-candidate Playwright **5 passed**。這是收斂進度證據，不等同十個 Module Independence Gate 已通過；server-side compatibility route removal 已於 2026-08-12 完成（ADR-0062），horizontal 層收斂與 external/hardware evidence 仍需逐項完成。

---

## 4. 未完成的工作

### 4.1 Local Pilot Admission — BLOCKED（Issue #20）

**兩個缺少的輸入，都無法由本 repository 取代：**

**（一）Pilot Configuration Authority**

2026-08-11 依專案擁有者指示，`~/.config/project-2026/` 下 11 個檔案與 `secrets/` 目錄全部刪除（刪除前已逐項列出；資料庫、volumes、備份均未動）。Local Pilot Readiness 的定義就是「唯一一份主機外部、權限私有的設定與 secret 來源」，缺它連 Gate 都進不去。

**（二）目標 Kiosk 實機**

以下無法用開發主機或 Playwright 取代。`docs/agents/p2-local-pilot-readiness.md` 明載：主機的 `/dev/video*`、`/dev/snd` 與可用的 NVIDIA GPU **都不是目標設備的證據**。

1. 目標裝置的麥克風、攝影機、瀏覽器權限、Chromium 版本、AudioWorklet 允收。
2. 內建 Silero VAD v5 模型／runtime／worklet 在目標裝置載入。
3. 250 ms 最短語音、1.2 s 結束靜音提交、30 s 上限、回音 cooldown ≤500 ms。
4. 連續十個 turn 無重疊、重複或 track／timer／context 洩漏。
5. 背景對話與吵雜店內的誤觸發／漏聽驗收。
6. 實體觸控與語音點餐、checkout outcome-unknown 復原、Payment Pending 交接。
7. Live Admin AV Test（2／5／30 秒）、自訂 prompt 與伺服器預設重設。
8. 八欄固定 enum 結果、voice-aligned 同一 `voice_turn_id`、攝影機不可用不阻擋 Voice。
9. 推論後 raw media／transcript 不存在；submitted failure 產生安全 Undetermined record；30 天 TTL 以可控 clock 驗證。
10. Kiosk 裝置憑證發放、撤銷與 store scope。
11. Pilot Recovery Objective：對與主 runtime 分離的備份副本觀測 RPO ≤1 小時、RTO ≤4 小時。

**重新進入條件**：建立主機外部 Pilot Configuration Authority → 重建 digest-pinned candidate → 重跑第 3.5 節全部項目 → 取得上列實機證據 → 宣告 Local Pilot Readiness → 關閉 #19／#20／#23。

### 4.2 P3 剩餘 — provider 憑證（Issue #26，`ready-for-human`）

[ADR-0037](docs/adr/0037-select-only-ready-project-analyst-profiles.md) 要求：CLI 版本落在釘住範圍、自動化憑證有效、non-interactive 執行可用、contract probe 回傳共同 JSON Schema。

四項都需要**實際安裝的 Codex／Claude／Grok 與自動化憑證**，依 2026-08-11 的決定目前不提供。

目前證據只涵蓋**關閉路徑**（無憑證必須 fail closed 且不切換），不涵蓋**成功執行一次分析**。提案工作流的限制機制已完成且經證明，但產生內容同樣需要就緒的 profile。

### 4.3 P4 Optimization Lab（Issue #30）

**修改工作包**

1. 建立與 Project Analyst 分離的 module／container 與 data store。
2. Voice Interaction Evidence 的 pre-persist 不可逆去識別化。
3. 30 天 evidence TTL、encryption-at-rest 介面、store scope 與 audit。
4. 單店單日 Daily Evidence Snapshot；當日標 partial／cutoff，IDs frozen。
5. Codex／Claude／Grok provider-native model／effort discovery；single analyzer、無 fallback。
6. 固定 classification 與 1–2 筆 observation／≥3 筆或可重現才給 guidance 的門檻。
7. Voice／RAG offline acceptance sandbox。
8. 固定六段 reference-only 報告，只引用 opaque evidence ID。
9. `optimization.evidence.read` ＋ 15 分鐘 step-up 與每次展開的 audit。
10. Provider-specific customer-evidence 授權／憑證／揭露／保存／egress audit。
11. API、network、mounts 與 credentials 強制 no production mutation。

**測試項目**

- Raw audio／member／device／session／order／payment／individual emotion 永不持久化。
- PII 去識別化成功；無法去識別就丟棄。
- 跨店 evidence／query 拒絕。
- 當日 cutoff 與歷史整日的時區邊界。
- Run 開始後新 evidence 不進 snapshot。
- Analyzer 不支援的 model／effort 在 egress 前拒絕。
- Analyzer 失敗無 fallback。
- 1、2 筆只給 Observation；3 筆相似或 synthetic 可重現才給 Reference Guidance。
- 矛盾證據 → Insufficient Evidence。
- Offline acceptance regression → guidance 被拒或標未驗證。
- 報告不含 transcript／answer 複本。
- 過期 evidence reference 不可用；report／evidence TTL 及衍生索引刪除。
- Summary permission、step-up 過期、audit 內容不含 conversation。
- Synthetic-only 為預設；缺客戶授權時阻擋 egress。
- Settings／RAG／Campaign／Recommendation／filesystem／DB mutation API 不存在的負向測試。

**已知風險**：第 10 項需要 customer-evidence 授權與部署證據，依 owner 決定暫不實作；local Ollama 僅能執行 synthetic/de-identified repository path，不能把 deferred customer path 標成已通過。

### 4.4 P5.1 Identity 與 Operations & Configuration（Issues #25、#31、#27）

**目前狀態：IN PROGRESS（repository boundary convergence）**。Identity 與 Operations
published interfaces、route ownership、least-privilege URL preparation 與 boundary tests
已落地；外部 Pilot authority、PostgreSQL runtime/restart/auth evidence 仍未宣告通過。

**Identity & Device Access（#25）** — 收斂 `admin_*`／`device_*`／`devices`／`fleet_*` 的 writers 與 readers 為唯一 Identity Capability Interface 與 versioned HTTP API；device／admin principals、sessions、RBAC、credentials、fleet access、audit 全部歸位；legacy principal／scope 相容性 telemetry 歸零後刪除。

測試：憑證發放／輪替／撤銷／過期、Device 與 Admin 匿名邊界與最小權限、store isolation、wrong-device／wrong-store 拒絕、session 重啟／過期／replay、audit 完整但不含 secret、PostgreSQL unique/foreign-key/concurrency/migration、Admin 與 Kiosk generated-client 呼叫端、legacy routes/imports/SQL/static/telemetry 歸零、Core 失敗時 fail closed。

**Operations & Configuration（#31）** — 收斂 commercial settings、audit、capability status、health/readiness 與 operator actions；取代 `config/profiles/local-pilot.env.example`；`UI_API/deploy/postgres` 能力移至 canonical `docker/`；`learning_data/settings.json` 的正式設定移入 Operations authority（測試改用 fixtures）；Admin raw fetch 改 generated client 並有有界失敗 UX。

測試：settings version/concurrency/validation/rollback projection、外部設定必填／缺漏／secret 洩漏、fresh 與 upgrade 的 PostgreSQL role/init/WAL/backup、Core readiness 對 Optional warm-up、Redis 與 shared-infrastructure degradation、health timeout／operator retry／audit、Admin raw fetch 與 static route literal 在此 scope 歸零、舊 deploy/profile/settings 路徑的負向測試。

**已完成的收斂項**：`prepare_local_persistence.py` 產生的 `database_url` 使用
`project_runtime`、`migration_database_url` 使用 `project_migrator`；Pilot application
不再需要 owning database role。`provision-pilot-database-role.sh` 與 migration
共同完成角色建立與授權；仍需在真正的 Pilot Configuration Authority 上重跑對帳證據。

### 4.5 P5.2 Member、Campaign、Recommendation Analytics（Issues #39、#36、#34、#28）

**目前狀態：IN PROGRESS（repository boundary convergence）**。三組 capability
contracts/interfaces 與 route/service consumers 已改走 published surface；各自的
PostgreSQL migration/backfill、consumer telemetry zero 與 Admin/Kiosk E2E ledger 尚未完成。

依序完成三個 capability，各自通過 Module Independence Gate。

**Member（#39）** — members、consent、preferences、session/history 唯一 owner；Guest ordering 不得依賴 Member 就緒。測試涵蓋註冊／登入／查無／重試、consent opt-in/out/version/retention、PII 加密／金鑰失敗／redaction、session 過期與 store isolation、history consent 與 guest 不存在、Member 依賴不可用時 Guest flow 仍成功、PostgreSQL migration/backfill/integrity/concurrency、legacy repository/route 歸零。

**Campaign & Promotion（#36）** — Campaign lifecycle/version/publication、promotion rule、push copy、active projection 唯一 owner，刪除 legacy promotion 平行真相。測試涵蓋允許與禁止的狀態轉換、內容編輯不改 lifecycle、publication 原子性、排程時區與起訖、促銷價驗證與伺服器權威、Campaign/Base push copy 解析、未驗證促銷宣稱被拒、並行編輯版本衝突、Kiosk 只讀 active projection、legacy promotion route/table/consumer telemetry 歸零。

**Recommendation & Interaction Analytics（#34）** — decision/events、commercial touch、interaction/effectiveness analytics 唯一 owner。測試涵蓋 eligibility/availability/cart 排除、placeholder 不產生 commercial touch、重複與 replay 事件 idempotency、Voice/recommendation/campaign 歸因、store scope／retention／事件順序、已接受的 metrics 定義能到達 Admin、已移除的目標設定／UI／API 負向測試、只透過 published interface 取用 Member 與 Campaign、legacy analytics repositories/routes/raw fetch 歸零。

### 4.6 P5.3 Ordering & Checkout（Issue #29）

**目前狀態：IN PROGRESS（repository boundary convergence）**。Ordering／Checkout
route 與 pricing/order adapters 已由 capability surface 進入；PostgreSQL-backed
candidate readiness 已完成，checkout outbox retry/dead-letter 與 cart revision
concurrency 已有 repository evidence；confirmation restart 與觸控／語音 E2E 證據尚未完成。

把 Entry、Session、Cart、Quote、Confirmation、Order、Payment Pending 收斂成一個 Ordering transaction deep module：伺服器端唯一的定價與可售性重驗、quote 與 order 權威、跨能力只用 published contracts、保留 idempotency、Confirmation Outcome Unknown、transactional outbox 與人工付款邊界，最後刪除 legacy route/service/repository。

測試涵蓋 Entry Flow 轉換／續行／逾時／改版、Guest 與 Member 選擇與 policy 載入逾時後備、Cart 增修刪與可售性／數量／scope、伺服器定價與促銷／費用／幣別與瀏覽器竄改拒絕、Quote snapshot/version/expiry/stale、Confirmation idempotency 與重複送出、commit 後逾時可查回同一 order、售罄／改價／依賴降級、交易 rollback 與 outbox 原子性／重試／dead letter、Order identity／history／Payment Pending 交接、confirmation 與 recovery 期間重啟、完整觸控與語音 E2E、AI/瀏覽器/跨能力 SQL 無交易寫入權、legacy cart/checkout/order API/consumer/telemetry 歸零。

### 4.7 P6 智慧能力（Issues #37、#38、#35、#33）

**目前狀態：IN PROGRESS（repository boundary convergence）**。Knowledge/RAG、Voice
與 Emotion 的 published surface、consumer boundary 與 P2 frozen contract 測試已存在；
provider degradation、index durability、target hardware 與 retention ledger 尚未完成。

順序固定為 **Knowledge/RAG → Voice Assistance → Emotion Diagnostics**。**P2 的顧客行為與紀錄是 frozen contract，不得被架構重構暗中改寫。**

**Knowledge/RAG（#37）** — knowledge lifecycle、publication attempts、published pointer、retrieval configuration/checks、index artifacts 唯一 owner；worker 走 durable jobs/outbox。測試涵蓋 store isolation 與 knowledge CRUD/版本衝突、原子發布、index/publication 失敗時保留舊 published pointer、durable job retry/resume/dead letter/restart、retrieval config 唯一 published 與無效刪除／還原、index 或 config 變更使 RAG check evidence 過期、provider/model 不可用與逾時且無 fallback、Admin generated client 與 legacy review/import/readiness 路徑歸零、index 路徑權限／checksum／保存與重建。

**Voice Assistance（#38）** — Voice Turn journal、STT/LLM/TTS orchestration、candidate set、order draft proposal、playback outcome、interaction evidence 唯一 owner；Silero 瀏覽器 adapter 維持 Kiosk consumer。測試涵蓋 turn ID/store/session scope 與狀態轉換、重試與 replay 不重做 assistant 也不產生重複草稿、STT/LLM/TTS 逾時與明確失敗、成功必須有可播放 TTS 且播放失敗保留文字但不算成功、攝影機降級不阻擋 Voice、candidate 菜單 allowlist 與模糊選項且不自動改購物車、P95 回應等待與 warm-up 拒絕、30 天去識別化 Voice Interaction Evidence TTL、P2 對話順序與 VAD 的 frozen regression、`/api/ask*` 未版本化路徑已隨相容面撤除（現為 `/api/v1/ask/stream`）／passive recorder／側寫入／直接 repository import 歸零。

**Emotion Diagnostics（#35）** — P2 的 model profiles、readiness、modes、capture、live test、records 與 TTL 收斂為 Emotion capability；R1 只作 adapter。測試涵蓋 P2 三模式、clip 長度與 ordering 邊界 regression、readiness 與 configured mode 分離、無並行積壓、voice-aligned AV 與未驗證的純音訊略過、submitted failure 安全紀錄、八欄／固定 enum／store scope／30 天 TTL、raw media 與 transcript 不存在、advisory-only（不得修改 Voice/Recommendation/Pricing/Ordering）、R1 不可用只降級 Emotion、ADR-0057 legacy 路徑不復活、Admin 與 Kiosk generated client 與 legacy routes/repositories 歸零。

通過三個 Gate 後實際計數應達 **10/10**。

### 4.8 P7 Legacy Closure 與 Project Completion（Issue #32）

**目前狀態：IN PROGRESS（static repository gates）**。production route horizontal
import zero-use、frontend shared transport、capability ownership inventory、巨型
`v1_routes.py` 的 capability-owned 拆分，以及**未版本化 `/api/*` 相容面的完全撤除**已通過；
完整候選成品矩陣與 external gates 仍未完成。

**零使用盤點**：Admin 與 Kiosk feature source 的 raw `fetch` 歸零（transport 實作只在共用 generated layer）；相容性 `/api/*` 的 static consumers 歸零；跨能力 repository import、SQL/write、global service、內部 HTTP loopback 歸零；legacy settings、tables/columns、jobs、fixtures、flags、allowlists、import exceptions 與 generated artifacts 都有替代或刪除證據；P2～P6 收斂債零阻塞項。

**相容面已撤除（2026-08-12）**。先前這裡把「沒有呼叫端」與「路徑已移除」寫成同一句：實測當時是 164 條路徑 = 93 條 `/api/v1` + 67 條仍在服務的 `/api/*`。67 條中有 60 條是同一個 handler 掛第二個前綴，7 條沒有 v1 對應（5 條 Optimization Lab、Admin health report 與兩個 incident 動作）已先取得版本化位置，`/api/admin/auth/me` 這唯一一份重複實作則連同其 transport 一併刪除。

撤除後從執行中的 stack 實測：**105 條路徑 = 101 條 `/api/v1` + 0 條未版本化 `/api/*`**，其餘 4 條是 `/`、`/kiosk`、`/pos`、`/admin` 頁面入口。決策與代價見 [ADR-0062](docs/adr/0062-serve-one-versioned-http-prefix.md)。`/api/demo/*` 與 `/api/debug/*` 是旗標控制的開發路由、commercial runtime 下 404，不屬於契約面。

因為相容面已不存在，原本「runtime telemetry 歸零」這個 gate 失去對象：它要證明的是沒有人在呼叫這些路徑，而現在呼叫一律 404。

**最終刪除**：巨型 `v1_routes.py` 已刪除，並拆成 `v1_context_routes.py`、
`v1_campaign_routes.py`、`v1_operations_routes.py`、`v1_knowledge_routes.py`、
`v1_fleet_routes.py` 及其他 capability-owned versioned modules 與共用支援模組；不得再原封搬回單一巨檔。
未版本化的相容 registration 與 `admin_identity_routes.py` 已刪除，`core_routes.py` 只保留頁面入口。
後續仍須刪除已清空的 horizontal `services/repositories/modules`、臨時架構 allowlists
與只為遷移存在的 runtime code；保留 migrations、ADR、audit 與必要歷史。

**capability 收斂清單**：`tests/test_architecture_boundaries.py` 的
`CAPABILITIES_STILL_ON_LEGACY_LAYERS` **已清空**：十個 capability interface 都不再
向 `services`/`repositories` 取值，規則現在是無 allowlist 的完全強制。這是
**程式碼歸屬**，不是 Module Independence —— Gate 仍要求 data authority、PostgreSQL、
重啟與 consumer 證據，計數維持 1/10。

收斂一個 capability 不會清空 `services/`。剩下的一部分是多個 capability 共用的
（`rag_provider`、`availability_service`、`postgres_utils`、observability），module
取用它們是跨能力依賴，不是 capability 沒有擁有自己的實作；把它們塞進某一個
capability 只會讓其他 capability 去 import 第三方的內部。這類共用基礎設施要各自
獨立處理。該清單只能縮短：capability 收斂後從清單刪除，測試會強制
要求刪除已收斂的項目；新項目一律不得加入。清單清空即為此段「horizontal 層已清空」的證據。

**全候選成品測試矩陣**（同一 commit／digests／config／migration／environment）：

1. Clean CI build 與 digest pinning
2. Fresh install migration、existing upgrade、reapply、checksum 對帳
3. Backend Python 3.10／3.12、Ruff、format、mypy、全部測試
4. PostgreSQL 與 Redis integration
5. Frontend typecheck、syntax、coverage、build、Playwright
6. Architecture imports、raw fetch、legacy literal、OpenAPI drift
7. Device／Admin auth、store scope 與 permissions
8. Member／Guest／Catalog／Campaign／Recommendation flows
9. 觸控與語音點餐、Checkout unknown outcome、Payment Pending
10. RAG publish／retrieval／recovery
11. Emotion modes／live AV／retention
12. Project Analyst isolation／proposals／providers
13. Optimization evidence／privacy／reports／egress
14. Docker read-only／cap-drop、restart／warm-up／degradation
15. Backup/restore 與 Pilot Recovery Objective
16. 目標 Kiosk VAD／noisy-store／STT／LLM／TTS／camera／soak
17. Secret／path／network／provider egress 與 audit
18. Raw-media 不存在與所有 30 天 TTL
19. Legacy telemetry 歸零
20. 十組 Module Independence 證據與 Admin/Kiosk 2/2

**Project Completion 條件**：

```text
Local Pilot Readiness: DECLARED for current artifact
Business Capability Modules passed: 10 / 10
Independent Product Frontends passed: 2 / 2
Legacy compatibility usage: ZERO
P2–P7 convergence debt: ZERO blocking items
P7 full-candidate verification: PARTIAL — local candidate executable rows passed; external rows blocked
```

### 4.9 獨立觀察項

| Issue | 內容 | 標籤 |
| --- | --- | --- |
| #47 | Pilot profile 下 `/docs`、`/redoc`、`/openapi.json` 已在 commercial runtime 關閉；development/test 保留，security probe 已納入三個 404。 | `ready-for-human`；待 owner 回填決策並關閉 |
| #48 | `base`／`application`／`runtime` 與 source-free `ai-base` 已分離；兩次完整 AI candidate build 的 app manifests 為 `sha256:8d0f2f449a4e15077850de2fcfcc7a55f4cc25325b228fa2a7036d3e6c0e62f2` 與 `sha256:403955b5d5b4ce36a53644b77aae10181fdc9e6789e9e83ae9b6cbc8495b48db`。第二次 source-only build 中 `requirements-ai.txt` COPY 與 pip install 層均為 `CACHED`，`test_dockerfile_layering.py` 與 `docker/scripts/test-ai.sh` 通過。 | `ready-for-agent`；repository evidence complete |

---

## 5. 阻塞清單（`ready-for-human`）

| Issue | 缺少的輸入 | 阻擋什麼 |
| --- | --- | --- |
| #20 | 主機外部 Pilot Configuration Authority | Local Pilot Admission |
| #20、#23 | 目標 Kiosk 實機、麥克風、攝影機 | Local Pilot Admission、P2 Functional Acceptance |
| #19 | 上列兩者 | P2 parent 關閉 |
| #26 | Codex／Claude／Grok CLI 與自動化憑證 | P3 provider 執行 |
| #30 | provider-native analyzer 憑證、customer-evidence authorization／retention review、加密 at rest 與 egress deployment evidence | P4 完整 Gate |
| #47 | 一個決定：關閉或明確接受 `/docs` 暴露 | Pilot 安全結論 |

**規則**：遇到這類阻塞時完成所有不依賴它的工作，記錄精確 Gate、已完成證據、缺少輸入與不可替代的原因，標 `ready-for-human`，不偽造、不 fallback、不把 blocked 改成 passed。若它阻擋固定順序，停止並詢問使用者。

---

## 6. 每個工作包的共用流程

### 6.1 Preflight

1. 確認 clean working tree、branch、HEAD、`origin/main`、open PR 與 CI。
2. 閱讀 parent/child issues、`CONTEXT.md`、相關 ADR 與前一 Gate evidence。
3. 建立 symbol、call path、route、repository、consumer 與 test inventory。
4. 補查 configs、Docker、migrations、HTML、generated artifacts、literal routes/settings。
5. 每一項分類為 `retain`、`refactor`、`migrate`、`purge` 或 `generated artifact`。
6. 記錄資料 owner、writers、readers、permission、failure、retention、observability 與 legacy replacement。

### 6.2 契約與紅燈測試

7. 固定 domain terms、use cases、Capability Interface、HTTP DTO／error／operation ID。
8. 固定 Core／Operational／Optional criticality 與 failure／degradation 行為。
9. 固定 principal、最小權限、store scope、retention 與 audit。
10. 先建立會失敗的 domain/unit、contract、permission、failure 與 consumer 測試。
11. 難逆轉的新決策先寫 ADR；只補清楚詞義時更新 `CONTEXT.md`。

### 6.3 權威實作

12. 建立 domain／application／interface／ports／adapters，禁止同 process loopback HTTP。
13. 先讓新 Capability Interface 成為唯一 writer，再遷移 readers。
14. Forward migration 必須支援 fresh install、existing upgrade、idempotent reapply 與 checksum validation。
15. Backfill 後核對 row count、identity、scope、checksum 或領域專屬對帳。
16. 更新 FastAPI/Pydantic OpenAPI，同 commit regenerate TypeScript contract。
17. Admin／Kiosk／worker／其他能力全部遷移；不保留手寫平行 DTO。
18. 加入 readiness、latency、error、degradation、audit 與 legacy usage telemetry。

### 6.4 零使用與刪除

19. 靜態架構測試證明無跨能力 repository import／SQL／write。
20. 前端靜態測試證明無 raw legacy route／fetch literal。
21. Runtime telemetry 與 E2E 證明 legacy consumer 為零。
22. 依 replacement → consumer migration → zero use → deletion 的順序移除 legacy。
23. 加入 404／absence／schema／static 負向測試，避免舊路徑復活。
24. 重大刪除先解析精確 target；禁止 broad glob、workspace root、home 或未驗證的環境變數。

### 6.5 PR 與證據

25. Focused tests → 完整本地支援檢查 → PR required checks。
26. PR 描述記錄 scope／non-scope、authority before/after、migration、failure、security、legacy replacement、recovery 與 evidence。
27. Required checks 全綠後 merge main、刪 branch、回填 Issue 與本文件。
28. 判斷後續變更是否讓先前證據 stale；需要時立即重跑。

### 6.6 一個 PR 的邊界

- 不跨兩個 capabilities 的 data ownership。
- Mechanical move 與 behavior change 分開。
- 不回退使用者變更。
- 不使用 `git reset --hard`、廣泛 checkout 或未解析的破壞性 glob。
- 不刪除 PostgreSQL volumes、backups、secrets 或未授權的 customer／business data。

---

## 7. 測試與證據標準

### 7.1 支援的命令

```bash
# 核心 Docker runtime
docker/scripts/test.sh          # 佔用中的 8000 port 需 APP_PORT=<free> 覆寫
docker/scripts/test-ai.sh

# 前端
cd UI_API/frontend
npm ci && npm run typecheck && npm run syntax && npm run test:coverage && npm run build && npm run test:e2e

# Pilot 硬化驗證（需先啟動 Pilot profile）
bash docker/scripts/verify-pilot-security.sh
```

GPU stack：

```bash
APP_GIT_REVISION=$(git rev-parse --short HEAD) docker compose --env-file .env \
  -f docker/compose.yaml -f docker/compose.ai.yaml -f docker/compose.ai-gpu.yaml \
  up --build -d --wait
```

Local Pilot 硬化 profile（`compose.pilot.yaml` 必須是最後一個 `-f`）與 Project Analyst sidecar overlay 的完整操作說明見 [`docker/README.md`](docker/README.md)。

### 7.2 Required checks

每個 PR 必須通過六項：Backend Python 3.10、Backend Python 3.12、PostgreSQL migration integration、Redis shared infrastructure integration、Frontend type and syntax checks、Shell syntax checks。

### 7.3 測試層級

| Layer | 必須證明 |
| --- | --- |
| Domain/unit | invariant、狀態轉換、enum、idempotency、邊界 |
| Interface | 跨能力呼叫只能用 published interface |
| HTTP contract | DTO、error、operation ID、permission、404 legacy absence |
| PostgreSQL | fresh、upgrade、reapply、transaction、constraint、對帳 |
| Redis/outbox/job | TTL、scope、lock、retry、重複投遞、dead letter |
| Frontend unit | reducer/controller、DOM/ARIA、failure/retry、無 stale state |
| OpenAPI/client | generated contract 無 drift、consumer 不手寫 DTO |
| E2E | 真正的 Admin/Kiosk consumer 與 server runtime |
| Docker | build、health、readiness、restart、warm-up、資源權限 |
| Security | principal、store isolation、secret/path/network、read-only/no mutation |
| Retention | raw absence、TTL、expiry、audit、衍生參照刪除 |
| Hardware/provider | 實際 device/model/credential、no fallback、失敗可見 |

SQLite 與 fake 可用於 unit tests，但**不得冒充** PostgreSQL、Redis、filesystem/index、provider 或目標設備的 integration 證據。

### 7.4 三條從實作中學到的測試規則

這三條是本輪工作中被違反後才補上的，寫在這裡避免重犯：

1. **工具缺席時跳過的 gate 等於沒檢查。** 曾有 13 個測試在 image 沒有 git 時 skip，而會 skip 的正是證明隔離的那些。要嘛把工具裝進 image，要嘛不要寫這個測試。
2. **安全邊界的每條規則都要有測試單獨依賴它。** 用突變測試驗證：把每個拒絕改成放行，如果測試仍全綠，那條規則就是裝飾。本輪對 evidence allowlist 做了 18 個突變、對 Pilot compose 契約做了 5 個。
3. **不要用字串搜尋證明「某物不存在」。** 解釋「為何不存在」的註解會被自己的檢查誤中。用 AST 檢查 import 與呼叫。

### 7.5 測試不得寫入原始碼樹

整套 backend 測試必須能在唯讀掛載上跑完。這是唯一能真正證明沒有測試污染工作區的方式：

```bash
docker run --rm --user 10001:10001 -v $PWD:/repo:ro -w /repo/UI_API \
  -e RUNTIME_DATA_ROOT=/tmp/p -e HOME=/tmp \
  project-2026:test python -m pytest -q -p no:cacheprovider
```

**同理，診斷指令不要以 root 加可寫掛載執行**。本輪曾因此讓 `load_settings` 用測試環境的值改寫 `UI_API/learning_data/settings.json`（含 `DATABASE_BACKEND: sqlite`），必須從 git 還原。

---

## 8. Evidence ledger

每個 Gate 通過時填一份。已完成的 ledger 見第 3 節；未來的用以下模板：

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

**後續變更影響任何欄位時，Gate 改為 `EVIDENCE_STALE` 並重跑。不得保留 `PASSED` 只加一句備註。**

---

## 9. Issue 對照

| Issue | 工作 | 狀態 |
| --- | --- | --- |
| #18 | P2～P7 Project Completion tracking | Open；總追蹤 |
| #19 | P2 parent | Open `ready-for-human` |
| #20 | Local Pilot Admission | Open `ready-for-human`；**BLOCKED** |
| #21 | Voice Dialogue reducer | Closed（PR #40） |
| #22 | Guest 入口與 stale artifact | Closed（PR #40／#42） |
| #23 | Silero target-device acceptance | Open `ready-for-human` |
| #24 | Emotion 契約與 purge | Closed（PR #40／#42） |
| #26 | P3 Project Core Brain | Open `ready-for-human`；repository scope 已通過 |
| #30 | P4 Optimization Lab | Open；repository foundation 已通過，完整 Gate blocked by external provider／customer-evidence inputs |
| #25／#31／#27 | P5.1 Identity／Operations | Open |
| #39／#36／#34／#28 | P5.2 三個 commercial capability | Open |
| #29 | P5.3 Ordering | Open |
| #37／#38／#35／#33 | P6 三個智慧能力 | Open |
| #32 | P7 Legacy closure 與 Project Completion | Open |
| #44 | Pilot 容器安全 | Closed（PR #46） |
| #47 | `/docs` 暴露 | Open `ready-for-human`；Option 1 已實作，待 owner 回填決策 |
| #48 | Dockerfile 層次順序 | Open `ready-for-agent`；source-free AI stage 已實作，cache evidence pending |

Issue 只能在驗收證據回填後關閉。若一個 Issue 同時含 repository 與目標設備 scope，應拆分或明確保留未完成 child，不能以 PR merged 直接關閉全部 scope。

---

## 10. 其他權威文件

| 文件 | 責任 |
| --- | --- |
| [`CONTEXT.md`](CONTEXT.md) | 領域詞彙。與本文件衝突時以它為準 |
| [`docs/adr/`](docs/adr/) | 決策紀錄。ADR-0001～0061 |
| [`AGENTS.md`](AGENTS.md) | Agent skills、issue tracker 與 triage labels |
| [`docs/agents/p2-local-pilot-readiness.md`](docs/agents/p2-local-pilot-readiness.md) | Local Pilot 證據帳本與未可允收清單 |
| [`docs/agents/p7-legacy-closure-inventory.md`](docs/agents/p7-legacy-closure-inventory.md) | P7 repository static boundary、legacy inventory 與不可替代輸入 |
| [`docs/agents/p4-p7-final-verification-matrix.md`](docs/agents/p4-p7-final-verification-matrix.md) | 20 項最終驗證矩陣、目前證據與阻塞分類 |
| [`docker/README.md`](docker/README.md) | Docker runtime、Pilot 硬化 profile、sidecar overlay 操作 |
| [`README.md`](README.md) | 專案入口 |
| [`UI_API/README.md`](UI_API/README.md) | 應用邊界 |
| [`R1-Omni/README.md`](R1-Omni/README.md) | R1 runtime 與權重 |

本輪相關的決策：[ADR-0021](docs/adr/0021-adopt-docker-first-immutable-pilot-delivery.md)、[ADR-0023](docs/adr/0023-organize-the-application-by-business-capability-contracts.md)、[ADR-0024](docs/adr/0024-separate-admin-and-kiosk-product-frontends.md)、[ADR-0034](docs/adr/0034-bound-the-project-core-brain-to-read-only-evidence.md)～[ADR-0040](docs/adr/0040-confine-non-core-proposals-to-new-isolated-modules.md)、[ADR-0047](docs/adr/0047-separate-project-analysis-from-customer-optimization-simulation.md)、[ADR-0060](docs/adr/0060-warm-capabilities-beside-the-service-not-in-front-of-it.md)、[ADR-0061](docs/adr/0061-run-the-pilot-on-a-read-only-container-contract.md)。
