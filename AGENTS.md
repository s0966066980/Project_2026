# Project_2026 工程協作規範

本文件是 Repository 內所有人員與自動化 Agent 的共同工作契約。若子目錄未提供更具體的 `AGENTS.md`，本文件適用於整個 Repository。

## 專案架構

目前採用 **Modular Monolith First**：

```text
Kiosk Web ─┐
           ├─ HTTPS / WebSocket ─ FastAPI Modular Monolith
Admin Web ─┘                         ├─ JSON compatibility storage
                                    ├─ PostgreSQL optional storage
                                    ├─ Ollama / Gemini
                                    └─ Emotion-LLaMA / R1-Omni
```

主要目錄責任：

- `UI_API/backend/api`：Route registry 與應用組裝。
- `UI_API/backend/routes`：HTTP/WebSocket transport、驗證、授權與 response mapping。
- `UI_API/backend/services`：Application service 與業務流程。
- `UI_API/backend/repositories`：JSON/PostgreSQL 資料存取 adapter。
- `UI_API/backend/schemas`：資料庫 schema 與 migration。
- `UI_API/frontend/kiosk`：顧客 Kiosk application。
- `UI_API/frontend/admin`：營運 Admin application。
- `UI_API/frontend/shared`：純通用 HTTP、realtime、design token 與 UI primitive。
- `Emotion-LLaMA`、`R1-Omni`：外部模型執行單元；不得混入核心商業 domain。
- `scripts`：本機啟動、資料庫備份與還原。
- `docs`：架構決策與商業化計畫。

長期目標目錄記錄於 `docs/architecture/TARGET_ARCHITECTURE.md`。禁止為了符合目標目錄進行 Big Bang 搬移。

## 模組與依賴規則

允許的依賴方向：

```text
API / Route
  ↓
Application Service
  ↓
Domain Policy
  ↓
Repository Port
  ↓
Infrastructure Adapter
```

- Route 只處理 transport、authentication、authorization、validation 與 response。
- Service 不得依賴 `fastapi.Request`、`Response` 或 HTTP status code。
- Repository 不得 import Service 或 Route。
- Domain policy 不得直接依賴 FastAPI、資料庫 driver、Ollama/Gemini SDK 或情緒模型。
- 外部 AI、儲存、realtime 與通知服務逐步以 Port/Adapter 隔離。
- Kiosk 與 Admin 不得互相 import business state、page state、DOM state 或 authentication state。
- Shared frontend 只能放 generic utility、contract、generated client、realtime client、design token 與 reusable primitive。
- 舊 `/api/*` 必須保持 backward compatibility；新 contract 使用 `/api/v1/*` 與明確 Pydantic schema。

## CodeGraph 工作方式

若 Repository root 或目標子專案存在 `.codegraph/`：

1. 理解或定位程式碼時，先使用 `codegraph explore "問題或 symbol"`。
2. 再使用 `rg` 驗證文字引用或補充非程式資產。
3. 修改跨模組 symbol 前，先檢查 callers 與 blast radius。
4. `.codegraph/` 是本機索引，不得提交 Git。

## Python Style

- 支援版本以 CI 設定為準；新語法不得超出 CI Python 版本。
- Module、Class、Function、Variable 使用英文；文件與使用者訊息使用繁體中文。
- 新 public function 應有型別註記；跨層資料契約優先使用 Pydantic model 或 TypedDict/dataclass。
- 禁止新增大型無型別 `dict` contract。
- I/O、外部 HTTP、模型推論與 blocking database call 不得阻塞 event loop。
- 不得使用 bare `except` 隱藏錯誤；記錄錯誤時不得輸出 Secret、完整 PII 或原始模型敏感內容。
- Ruff 與 mypy 採漸進式擴大範圍；不得用大量 `noqa`、`type: ignore` 或全域關閉規則掩蓋問題。

## JavaScript / TypeScript Style

- 現有 DOM contract 在明確 migration ADR 前保持穩定。
- 新模組優先 TypeScript 或 `// @ts-check` JavaScript，避免新增隱式 `any`。
- 禁止 Kiosk 與 Admin 共用 feature controller 或 mutable business state。
- API URL、錯誤處理與 credential handling 應集中到 application client，不得持續散落 raw `fetch`。
- 使用 `textContent` 或明確 escaping；不得將未驗證資料直接放入 `innerHTML`。
- 長期 credential 不得存入 URL 或 `localStorage`。

## Testing Requirements

行為修改必須新增或更新測試。合併前至少執行：

```bash
cd UI_API
MEMBER_STORAGE_BACKEND=json DATABASE_URL= pytest -q tests

cd frontend
npm ci
npm run typecheck
npm run syntax

cd ../..
bash -n scripts/start_emotion_llama.sh
bash -n scripts/start_r1_omni.sh
```

- Route 變更：Route/contract test。
- Service 變更：Service test。
- Repository 變更：JSON/PostgreSQL boundary test。
- Migration 變更：forward、checksum、資料驗證與 rollback/recovery 文件。
- 關鍵 Kiosk/Admin 流程後續由 Playwright smoke test 保護。
- 未執行的測試必須標示 `NOT RUN`，不得描述為通過。

## Migration Rules

- 所有 schema 修改必須使用新的、不可變的 versioned migration。
- 已套用 migration 不得修改；checksum mismatch 必須視為部署阻斷。
- 採 expand → dual write/backfill → verify → switch read → contract。
- 破壞性 migration 必須有備份、restore、rollback 或 roll-forward 計畫。
- Milestone 0 不執行會員 phone PK、UUID、tenant 或 PII encryption migration。

## Security Rules

- 不得提交 Secret、Token、Password、私鑰、模型權重、真實會員資料或 production dump。
- Infrastructure secret 只能來自 environment 或 Secret Manager。
- Authentication 與 authorization 必須由 server 強制執行。
- 新 Admin 權限需具 tenant/store scope；新 Kiosk credential 需可輪替並綁定 device。
- PII log 預設遮罩；手機號碼不得作為長期公開 Domain ID。
- 新 input、upload、webhook 與 AI output 都必須驗證大小、型別、權限與信任邊界。
- CORS、rate limit、timeout、retry、idempotency 與 audit 根據風險明確設定。

## Git Rules

- `main` 必須保持可部署；功能工作使用明確 branch。
- 每個 PR 只處理一個 Milestone 或單一明確目的。
- Commit 不得混入 `.codegraph`、截圖、runtime data、cache、模型或無關格式化。
- 禁止未經明確授權使用 `git reset --hard`、force push 或改寫共享歷史。
- Commit 前檢查 `git status`、`git diff --check` 與測試結果。

## Codex 工作流程

1. 檢查 branch、status、最近提交與既有使用者修改。
2. 閱讀實際程式碼與依賴圖；README 只作參考。
3. 列出 findings、風險、修改檔案、不修改檔案、migration 與 test strategy。
4. 使用小步驟與測試保護進行修改。
5. 執行與風險相稱的完整驗證。
6. 交付 Summary、Changed Files、Architecture Impact、Verification、Security Review、Remaining Risks 與 Next Milestone。

## 禁止事項

- 禁止 Big Bang Rewrite 或一次搬動長期目標全部目錄。
- 禁止未經 ADR 將 Modular Monolith 拆成大量 Microservices。
- 禁止破壞 `/kiosk`、`/admin`、既有 `/api/*`、WebSocket、會員、推薦、RAG、語音或情緒流程。
- 禁止在沒有 adapter 必要性的情況修改 Emotion-LLaMA 或 R1-Omni 核心模型。
- 禁止以刪除功能、停用測試或大量 ignore 讓 CI 變綠。
- 禁止未經 migration 直接修改 production database schema。
