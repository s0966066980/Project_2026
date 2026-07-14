# Project_2026 Agent 協作規範

本文件是 Repository 內人員、Codex 與其他自動化 Agent 的預設工作契約。子目錄若有更具體的 `AGENTS.md`，以距離目標檔案最近的規則為準。

## 1. 工作原則

- 先讀目標檔案、鄰近模組與直接依賴；**局部任務不需要每次完整稽核整個 Repository**。
- 優先做最小、可驗證、可回復的修改；禁止為了「整理架構」進行無關搬移或大量格式化。
- README 描述已存在的事實；未完成項目放 `docs/FUTURE_MODULES.md`。
- 重大且長期的架構選擇才新增 ADR；一般 refactor、rename 或小型實作不需要 ADR。
- 有合理預設時直接執行，不重複要求確認；只有破壞性操作、需求衝突或缺少關鍵資訊時才停下詢問。

## 2. 任務規模與預設流程

### A. 局部文件、樣式或低風險修正

1. 閱讀目標檔案與直接引用。
2. 修改最小範圍。
3. 執行最接近的語法或格式檢查。
4. 回報：`Summary`、`Verification`、必要風險。

不需要先輸出完整計畫、架構報告或全專案 dependency map。

### B. 單一模組功能或 Bug

1. 閱讀入口、service/controller、資料流與現有測試。
2. 先建立可重現問題的測試或明確驗收條件。
3. 修改單一責任範圍。
4. 執行目標測試，再視影響擴大驗證。

### C. 跨模組、公開 API、安全、資料庫或部署變更

1. 先列出簡短計畫、影響範圍、相容策略與測試策略。
2. 檢查 callers、資料契約、權限與 rollback/roll-forward。
3. 更新受影響的 README、`docs/ARCHITECTURE.md`、治理文件或 ADR。
4. 執行完整相關驗證。

## 3. 現行架構邊界

專案採 **Modular Monolith First**：

```text
Kiosk Web ─┐
           ├─ HTTP / WebSocket ─ FastAPI Modular Monolith
Admin Web ─┘                         ├─ JSON compatibility storage
                                    ├─ PostgreSQL
                                    ├─ Ollama / Gemini
                                    └─ Emotion-LLaMA / R1-Omni
```

責任分工：

- `UI_API/backend/routes`：HTTP/WebSocket、authentication、authorization、validation、response mapping。
- `UI_API/backend/services`：Application workflow 與業務規則。
- `UI_API/backend/repositories`：JSON/PostgreSQL 與其他資料來源 adapter。
- `UI_API/backend/schemas`：資料庫 schema、migration 與跨層 contract。
- `UI_API/frontend/kiosk`：顧客點餐流程。
- `UI_API/frontend/admin`：營運與維運流程。
- `UI_API/frontend/shared`：通用 client、realtime、design token、UI primitive；不得放 Kiosk/Admin 專屬 business state。
- `Emotion-LLaMA`、`R1-Omni`：獨立模型執行單元，不得承擔核心商業資料寫入。
- `scripts`：本機 orchestration 與資料庫維運。
- `tools`：非 production path 的開發或一次性工具。
- `docs`：架構決策、商用治理與後續模組規劃。

詳細架構見 `docs/ARCHITECTURE.md`。

## 4. 依賴規則（Local Pilot Modular Monolith）

部署固定為**單店本地端 Kiosk Pilot**。禁止新增 Docker Runtime、Kubernetes、Microservices、Cloud-first、Kafka/RabbitMQ、多區域或不必要 infrastructure abstraction。

允許方向：

```text
Frontend (v1Client only)
    ↓ HTTP / WebSocket
/api/v1/* Module Router (api.py)
    ↓
Module Application API (application.py)
    ↓
Domain / Port
    ↓
Adapter (PostgreSQL, Local Storage, Provider)
```

### Architecture Boundary Rules

- Route 只呼叫 Module Public Application API；**不得** import Repository、PostgreSQL adapter、Provider client。
- Module 之間只可呼叫對方 **Public Application API** 或 Domain Event；**不得** import 他模組 Repository / Adapter。
- Provider HTTP（Ollama、Emotion、外部 SDK）只允許出現在 `integrations/*` adapters。
- Module 公開面：Application API、Typed DTO、Port、Domain Event。不得公開 Repository、DB Row、Provider Client、File Path。
- 只有存在真實邏輯時才建立 `domain.py` / `ports.py` / `adapters/`；禁止空殼檔。
- Backend 模組間**不得**用本機 HTTP 互相呼叫。
- Compatibility re-export 最多保留一個 milestone，下一個 milestone 必須刪除。

### Frontend API Rule

- Frontend 只存在 `UI_API/frontend/`；所有 request 經 `shared/api/v1Client`。
- 禁止任意 `fetch("/api/...")`、axios 直呼 legacy path（除 v1Client 本體）。
- Frontend 不得計算最終價格、決定 promotion eligibility、order state、member scope、payment result。

### PostgreSQL Local Pilot Rule

- `local-pilot`：PostgreSQL 為**唯一**商業資料 Source of Truth。
- 禁止 runtime JSON 商業資料、禁止 DB failure silent fallback 到 JSON。
- 已發布 migration `0001`–`0011` 不可改寫；只可 forward migration。
- Object **metadata** 存 PostgreSQL；binary 存 local object storage。

### Dead Code / Docs / Test Rules

- 刪除未使用 import、未註冊 route、無 runtime caller 的 service/adapter、完成任務 roadmap/TDD 文件。
- 文件 Single Source：`README`、`docs/PROJECT_STATUS.md`、`ARCHITECTURE`、`DATABASE`、`API_MODULES`、`LOCAL_OPERATIONS`、`TEST_STRATEGY`。
- 測試以商業風險為準；刪除檔案存在/Markdown 字串/SQL keyword/trivial DTO 測試。

## 5. 程式與安全規則

### Python

- 新 public function 優先加入型別註記。
- 大型跨層資料契約使用 Pydantic model、TypedDict 或 dataclass，避免擴大無型別 `dict`。
- Blocking I/O、模型推論與同步資料庫操作不得直接阻塞 event loop。
- 不使用 bare `except` 隱藏錯誤。
- 不以大量 `noqa`、`type: ignore` 或關閉規則讓檢查通過。

### JavaScript / TypeScript

- 現有 DOM contract 在明確 migration 前保持穩定。
- 新模組優先 TypeScript 或 `// @ts-check` JavaScript。
- API URL、credential handling 與通用錯誤處理集中於 client。
- 未驗證資料不得直接寫入 `innerHTML`；優先使用 `textContent` 或明確 escaping。
- 長期 credential 不得放在 URL 或 `localStorage`。

### Security

- 不提交 Secret、Token、Password、私鑰、模型權重、真實會員資料或 production dump。
- Authentication 與 authorization 必須由 server 強制執行。
- PII log 預設遮罩；手機號碼不作為長期公開 Domain ID。
- 新 input、upload、webhook 與 AI output 需檢查大小、型別、權限與信任邊界。
- Schema 變更使用新的 versioned migration；已套用 migration 不直接改寫。

## 6. 驗證矩陣

依變更範圍執行，不必每次跑全部命令。

| 變更 | 最小驗證 |
| --- | --- |
| Markdown | 檢查相對連結、命令與路徑 |
| Python route/service/repository | 目標 `pytest`；必要時擴大至 `pytest -q tests` |
| Python core/API/utils | `ruff check`、`ruff format --check` 與對應測試 |
| Typed Python 範圍 | `mypy` |
| Frontend | `npm run typecheck`、`npm run syntax` |
| Shell | `bash -n <changed-script>` |
| Migration | migration tests、資料驗證與 recovery 說明 |
| 關鍵 Kiosk/Admin 流程 | 對應 smoke/E2E；尚未建立時明確標示缺口 |

完整 CI 基線以 `.github/workflows/ci.yml` 為準。

## 7. Git 與交付

- 保留既有使用者修改；禁止未經授權使用 `git reset --hard`、force push 或改寫共享歷史。
- Commit/PR 只包含單一目的，不混入 cache、runtime data、模型、截圖或無關格式化。
- 修改前確認 `git status`；提交前檢查 `git diff --check`。
- 未執行的測試標示 `NOT RUN`，不得描述為通過。

預設交付格式保持精簡：

```text
Summary
Verification
Risks / Follow-up（只有需要時）
```

只有跨模組、架構、安全、資料庫或部署變更，才增加：

```text
Architecture Impact
Migration / Compatibility
Security Review
```

## 8. 禁止事項

- 禁止 Big Bang Rewrite。
- 禁止未經 ADR 將 Modular Monolith 拆成大量 Microservices。
- 禁止破壞 `/kiosk`、`/admin`、既有 `/api/*`、WebSocket、會員、推薦、RAG、語音或情緒流程。
- 禁止為了讓 CI 通過而刪除功能、停用測試或加入大量 ignore。
- 禁止在沒有 adapter 必要性的情況修改 Emotion-LLaMA 或 R1-Omni 核心模型。
