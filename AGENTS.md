# Project_2026 — Codex / Agent Working Contract

本文件是 Repository 內 Codex 與其他 coding agent 的主要工作規則。目標是：**小範圍、可驗證、可回復、低 token**。

`AGENT.md` 只提供入口；規則以本文件為準。子目錄若新增更具體的 `AGENTS.md`，以距離目標檔案最近的規則優先。

## 1. Repository 定位

- 主要產品程式：`UI_API/`。
- Kiosk：`UI_API/frontend/kiosk/`。
- Admin：`UI_API/frontend/admin/`。
- 共用 frontend：`UI_API/frontend/shared/`。
- Backend：`UI_API/backend/`。
- 可選模型：`Emotion-LLaMA/`、`R1-Omni/`；除非任務明確涉及 provider / adapter，否則不要讀取或修改模型核心。
- `tools/` 是 demo、維運或一次性工具，不是 production path。
- 部署方向是單店本地端 / LAN 原生 process；不要自行導入 Docker、Kubernetes、microservices、Kafka 或 cloud-first infrastructure。

## 2. 先辨識現況，不要假設重構已完成

目前是 **Transitional Modular Monolith**：

```text
目前既有路徑
Route → Service → Repository → JSON / PostgreSQL

目標模組路徑
Route → modules/<domain>/application.py
      → Domain / Port
      → Adapter / Integration
```

已知現況：

- Entry：`UI_API/main.py` → `backend/app_factory.py` → `backend/api/router.py` → `backend/api/route_registry.py`。
- Identity 已開始抽離到 `backend/modules/identity/`。
- `backend/services/admin_identity_service.py` 是暫時相容 shim；不要擴大 shim 的責任。
- `/api/v1` 已有 typed contracts，但 `backend/routes/v1_routes.py` 仍直接依賴部分 service / repository；不要把「完全模組化」當成已完成。
- Frontend 同時存在 legacy `/api/*` 與 typed `/api/v1/*`；只做漸進切換，不做 Big Bang rewrite。

## 3. Token-efficient Loop

每個任務使用下列 loop。一次只解決一個可驗證目標。

```text
Observe → Decide → Change → Verify → Review → Continue / Stop
```

### Loop 0 — Bootstrap（每個任務只做一次）

1. 執行 `git status --short`，保留使用者既有修改。
2. 讀本文件。
3. 把需求整理成 4 行工作記憶：

```text
Goal: 單一目標
Scope: 允許修改的模組 / 檔案
Invariant: 不可破壞的 API、DOM、資料或安全邊界
Acceptance: 可執行或可觀察的完成條件
```

4. 用 `rg` / `rg --files` 窄範圍找入口、symbol、直接 caller 與最近測試。
5. 不要先完整掃描 Repository；局部任務不要讀 `Emotion-LLaMA/`、`R1-Omni/`、大型資料、模型權重、圖片或生成檔。

### Loop N — Execute

#### A. Observe

只讀：

- 目標檔案。
- 直接 caller / dependency。
- 同模組公開 contract。
- 最近的相關測試。

大型檔案只讀必要區段；不要反覆貼回已讀內容。

#### B. Decide

在修改前確認：

- 本 loop 只有一個 objective。
- 預計修改不超過約 6 個 source files；超過時先切 checkpoint。
- 是否影響 API、資料、權限、migration、DOM contract 或跨模組相容性。
- 最小驗證命令是什麼。

只有跨模組、安全、資料庫、部署或公開 API 變更，才需要先輸出簡短 plan。

#### C. Change

- 做最小 patch，不順手重構無關程式。
- 保持現有 public API、URL、DOM id/class、WebSocket event、資料格式相容，除非 acceptance 明確要求 migration。
- 不做全檔格式化，不修改無關命名。
- Bug 優先補可重現測試或明確 regression assertion。
- 新 abstraction 必須解決真實重複或邊界問題；禁止建立空殼 `domain.py`、`ports.py`、`adapters/`。

#### D. Verify

先跑 target check，再視影響擴大。執行命令前先確認路徑與 dependency file 存在。

#### E. Review

至少檢查：

```bash
git diff --check
git diff --stat
```

再閱讀實際 diff，確認：

- 沒有無關變更。
- 沒有 secret、token、真實會員資料、dump、模型或 runtime data。
- 沒有新增跨層反向依賴。
- 未執行的測試標示 `NOT RUN`，不得描述為通過。

#### F. Continue / Stop

繼續下一 loop 的條件：

- Acceptance 尚未達成。
- 下一步仍在原 Scope。
- 有新的可驗證 objective。

停止條件：

- Acceptance 已達成且 target checks 通過。
- 下一步會擴大成另一個任務。
- 缺少必要環境、credential 或外部服務；回報 blocker，不要為了繞過環境而改壞程式。

## 4. Backend 邊界

### Transport

`backend/routes/` 與 `backend/api/`：

- 處理 HTTP / WebSocket、authentication、authorization、validation、rate limit、request / response mapping。
- 新 code 不在 route 直接讀寫 JSON、PostgreSQL、檔案或 provider。
- Route 應呼叫 module Application API；尚未切換的 domain 可呼叫既有 service，但不要新增 route → repository 依賴。
- Demo、test、debug route 在 pilot / staging / production 必須 fail closed。

### Application / Module

`backend/modules/<domain>/application.py` 或既有 `backend/services/`：

- 負責 use case、workflow、交易順序與業務規則。
- 新 bounded context 優先建立清楚的 module public Application API。
- Module 之間只呼叫對方公開 Application API、typed DTO 或 domain event。
- 不 import 其他 module 的 repository、adapter、internal `_*.py`。
- Compatibility shim 只能維持相容，不新增新業務功能；完成 callers cutover 後應刪除。

### Domain / Contract

- 純規則避免依賴 FastAPI、DB driver、HTTP client、檔案路徑或全域 config。
- 跨層資料使用 Pydantic model、dataclass、TypedDict 或清楚型別；避免擴大無型別 `dict`。
- 已發布 migration 不改寫，只新增 forward migration。

### Repository / Adapter / Integration

- `repositories/`、module `adapters/` 與 `integrations/` 負責 I/O。
- Repository 不 import route；不承擔推薦、促銷、會員 eligibility 等商業決策。
- Ollama、Gemini、Emotion、Payment、POS 與外部 SDK / HTTP 只放在 integration / adapter。
- Backend module 間不得用本機 HTTP 互相呼叫。
- `pilot`、`staging`、`production`：PostgreSQL 是商業資料 Source of Truth；禁止 DB failure 靜默 fallback 到 JSON。
- AI、RAG、語音、情緒 provider 失敗不得阻擋 checkout。

## 5. Frontend 邊界

### Kiosk

`UI_API/frontend/kiosk/`：

- 顧客點餐、購物車、會員、推薦、語音、互動事件與付款 UI。
- 畫面 state、controller、feature 優先留在 kiosk 內。

### Admin

`UI_API/frontend/admin/`：

- 營運設定、會員、RAG、活動、推薦事件、供應、健康與權限管理。
- `admin.js` 目前仍是大型 orchestrator；新功能優先放入對應 `features/` 或 `modules/`，避免繼續膨脹。

### Shared

`UI_API/frontend/shared/`：

- 只放真正共用的 API / HTTP / realtime client、hook、UI primitive、design token。
- 不放 Kiosk 或 Admin 專屬 business state。
- Kiosk 與 Admin 不互相 import。
- 新 API 呼叫集中到 client；不要新增散落 `fetch()`。
- 不把 server business rule 搬到 browser。價格、promotion eligibility、order state、member scope、payment result、permission 以 server 為準。
- 未驗證資料不要直接寫入 `innerHTML`；優先 `textContent` 或明確 escape。
- 長期 credential 不放 URL 或 `localStorage`。
- 現有 DOM id/class 是相容 contract；沒有 migration 計畫時不要任意改名。

## 6. 最小驗證矩陣

先確認命令依賴的檔案存在；目前 CI 有 baseline drift，不能盲目照 workflow 執行。

| 變更範圍 | 最小驗證 |
| --- | --- |
| Markdown | 檢查相對連結、路徑、命令與檔名 |
| Python route / service / module / repository | 最近的 `pytest -q tests/test_*.py` |
| App 組裝 / config | import smoke + 相關 target tests |
| Frontend JS / TS | `npm run typecheck`、`npm run syntax` |
| Frontend behavior | `npm run test`；關鍵跨頁流程才跑 `npm run test:e2e` |
| Frontend build / entry | `npm run build` |
| Shell | `bash -n <changed-script>` |
| Migration / PostgreSQL | 對應 integration test、forward migration、資料驗證與 rollback/roll-forward 說明 |
| Security / auth / scope | target security tests，檢查 fail-closed 與權限邊界 |

Backend 常用環境：

```bash
cd UI_API
APP_ENV=test MEMBER_STORAGE_BACKEND=json DATABASE_URL= ENABLE_NGROK=false \
pytest -q tests/test_target.py
```

App import smoke：

```bash
cd UI_API
APP_ENV=test MEMBER_STORAGE_BACKEND=json DATABASE_URL= ENABLE_NGROK=false \
python -c "from main import app; assert app.title == 'Smart Ordering Kiosk API'"
```

Frontend：

```bash
cd UI_API/frontend
npm run typecheck
npm run syntax
npm run test
npm run build
```

不要因為局部修改而重裝全部 `UI_API/requirements.txt`；它包含大型 RAG / STT / vision dependencies。缺少環境時回報 `NOT RUN`，不要為了跑無關測試擴大 dependency 變更。

## 7. 目前 baseline drift（先辨識，勿在無關任務中順手修）

目前 `main` 有已知不一致：

- `.github/workflows/ci.yml` 仍引用已移除的 `UI_API/requirements-ci.txt`、`UI_API/pyproject.toml` 與部分 local / PostgreSQL scripts。
- `UI_API/tests/test_local_operations.py` 仍 assert 已移除的 `scripts/local/*`、deployment scripts。
- 因此完整 CI / full suite 可能在產品程式測試前失敗。

除非 Goal 是 CI / Operations alignment，否則：

1. 不重建已刪除的整套工具鏈。
2. 不刪除測試來讓 CI 綠燈。
3. 只執行與當前變更相關且路徑存在的 target checks。
4. 在交付結果列出 baseline blocker，與本次 patch 的結果分開。

## 8. 安全與資料規則

- 不提交 secret、token、password、私鑰、真實會員資料、production dump、模型權重或大型生成檔。
- Authentication / authorization 必須由 server 強制執行。
- PII log 預設遮罩；手機號碼不是長期公開 Domain ID。
- 新 input、upload、webhook、AI output 檢查大小、型別、權限與信任邊界。
- Blocking I/O、同步 DB、模型推論不可直接阻塞 async event loop；必要時用 thread / worker / async adapter。
- 不使用 bare `except` 隱藏錯誤。
- 不用大量 `noqa`、`type: ignore`、停用 lint 或刪測試來讓檢查通過。

## 9. Git 與變更範圍

- 保留使用者既有修改。
- 禁止 `git reset --hard`、force push、改寫共享歷史。
- 一個 commit / PR 只處理一個目的。
- 不提交 cache、log、runtime data、Chroma data、node_modules、模型、dump 或無關格式化。
- 修改前看 `git status --short`；交付前看 `git diff --check` 與實際 diff。
- 破壞性操作、公開 contract 破壞或資料不可逆 migration 才需要停下確認。

## 10. 預設交付格式

保持精簡：

```text
Summary
- 做了什麼

Verification
- PASS: 已執行且通過
- NOT RUN: 未執行與原因

Risks / Next
- 只有實際存在時列出
```

跨模組、安全、資料庫、部署或公開 API 變更才增加：

```text
Architecture Impact
Compatibility / Migration
Security Review
```

不要輸出完整思考過程，不重述已讀檔案內容；只回報決策、patch、驗證與剩餘風險。
