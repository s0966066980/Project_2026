# 下次更新的交接

2026-08-14。從 `e308a12` 到 `fe81399`，十一個提交，CI 六個 job 全綠。

這份文件記錄**還沒做的兩項**，以及做它們之前需要知道的事實。每一條事實都是量過的，不是推測——寫下來是因為重新量一次要花掉半天。

---

## 一、七項清單的現況

| # | 項目 | 狀態 |
| --- | --- | --- |
| 1 | 語音紀錄 | ✅ 0 → 25 筆 |
| 2 | 推播成功率／點餐明細 | ✅ 曝光 0 → 3,613、明細 0 → 12 筆 |
| 3 | 移除進階分析與專案核心大腦 | ✅ ADR-0066 |
| 4 | 推薦事件清除鈕 | ✅ 保留 30 天＋稽核 |
| 5 | **活動管理重構** | ❌ 未開始，等樣張 |
| 6 | Kiosk 語音／推薦解耦 | ✅ |
| 7 | **例行排程** | ❌ 做到一半，已還原 |

---

## 二、項目 7：例行營運診斷排程

### 目標

操作者設定一則「例行公事 prompt」，系統每天自動跑一次今日診斷：讀當天所有語音對話 → 分析重點 → 查 RAG 是否已涵蓋 → 沒有的話提議新的 RAG 內容給操作者審查。

### 已經蓋好的部分（不要重寫）

**整條鏈都在 `modules/optimization_lab/`。** 這是 2026-08-14 那次調查最重要的發現：這個功能並不需要新建，只需要排程。

| 環節 | 實作 |
| --- | --- |
| 例行 prompt | `create_diagnostic_question` / `list` / `update` / `delete`（CRUD 已存在） |
| 分析今日語音 | 報告區塊 `voice_outcomes`、`voice_interaction_analysis` |
| 重點整理 | 區塊 `findings_and_guidance` |
| 查 RAG 是否解決 | 區塊 `rag_observations` |
| 提議 RAG 內容 | `_build_knowledge_candidate()`，專找 `classification == "RAG Knowledge Gap"` |
| 操作者審查 | `pending_candidate` / `edit_candidate` / `abandon_candidate` |
| 核准後寫入 RAG | `confirm_candidate()` → 知識庫新增或更新 |

執行入口是 `OptimizationLabModule.simulate(scope, store_date, timezone_name, profile_id, model, effort, data_scope, question_id)`。

實測（2026-08-14，修好語音證據之後）：

```text
evidence_summary   {"status": "ready", "count": 1}
voice_outcomes     {"completed": 1, "failed": 0, "retry_or_correction": 0}
rag_observations   {"hits": 0, "misses": 1}
findings           []
```

### 缺的只有兩樣

**1. 排程本身。** `run_worker.py` 只輪詢待處理工作，沒有任何 cron／schedule 機制；`執行今日診斷` 是一顆手動按鈕。

**2. RAG 缺口永遠不會被偵測到。** 這是比排程更根本的問題，排程做完也不會有候選產出：

- `_classify_findings` 只為**有 `failure_type`** 的證據列產生 finding；`completed` 的語音 turn 是 `""`
- `RAG Knowledge Gap` 明確需要 `failure_type == "rag_miss"`
- `VoiceTurnModule._enqueue_terminal_evidence` 送出的 terminal payload 只有七個欄位，**沒有 `rag_outcome`**
- 再往下：**語音助理根本不查 RAG**。`modules/voice_turn/` 裡沒有任何 RAG 呼叫

所以 `rag_observations: {"misses": 1}` 其實是把 `not_run` 當成 miss 在算。**要讓「提議新增 RAG 內容」真的發生，得先讓語音回答時去查 RAG 並記錄結果**——那是一個新能力，不是接線。

### 上次做到哪、為什麼還原

已寫、已還原的四個檔案：

- `models/worker_jobs.py` — `ALLOWED_JOB_TYPES` 加入 `"diagnostic.daily"`
- `models/settings_contract.py` — 加入 `DAILY_DIAGNOSTIC_QUESTION_ID`、`DAILY_DIAGNOSTIC_HOUR`
- `config.py` — 兩個預設值（`""`、`4`）
- `services/worker_handlers.py` — `handle_daily_diagnostic` 與註冊

還原的原因：**handler 呼叫了 `operations.get_setting()`，那個函式不存在**，而且「到期入列」那段完全沒寫。留著就是一份壞掉的半成品。

### 重做時的設計（已想清楚，照做即可）

**冪等性免費。** `enqueue_job` 對「相同 tenant + job_type + idempotency_key」直接回傳既有工作（`modules/operations/_worker.py:100-108`），所以用 `daily-diagnostic-{store_id}-{store_date}` 當鍵，重啟或多個 worker 都不會重跑。

**到期入列放在 worker cycle 裡。** 每一輪檢查：店家本地時間是否已過設定的小時、今天的鍵是否已存在；沒有就入列。不需要 cron。

**不要替操作者挑問題。** 沒有指定 `DAILY_DIAGNOSTIC_QUESTION_ID` 時就不跑，並回 `daily_diagnostic_not_configured`（不可重試）。報告被歸給一個沒人選的 prompt，比沒有報告更糟。

**設定讀取要先確認方法。** `capabilities/operations_configuration/interface.py` 目前**沒有** `get_setting()`。要嘛加一個，要嘛用既有的設定文件讀法——動手前先查清楚，上次就是卡在這裡。

**重試語意分開。** 設定未完成 → 不可重試（重試一個沒設定的值只是燒掉 attempt 預算）；分析器失敗 → 可重試。

---

## 三、項目 5：活動管理重構

### 已確定的決策（不要重新討論）

| 問題 | 決定 |
| --- | --- |
| 新的顯示位置清單 | 菜單卡片、餐點詳情、首頁活動區、購物車活動區 |
| AI 推薦、語音優惠回答 | **移除**。活動只負責顯示 |
| 優惠價 | 仍要即時更新 |
| 預覽形式 | Admin 內嵌即時預覽，用 kiosk 同一組元件渲染 |

### 動手前必須知道的事實

**目前六個選項裡有四個是裝飾。**

| 位置 | kiosk 端消費點 | 實際效果 |
| --- | --- | --- |
| `pos_home_banner` | 4 | ✅ 真的渲染 |
| `kiosk_cart_banner` | 3 | ✅ 真的渲染 |
| `menu_card` | 3 | ⚠️ 只是觸點來源標籤，不是渲染位置 |
| `item_detail` | **0** | ❌ 完全沒有消費點 |
| `recommendation` | 3 | 要移除 |
| `voice` | 2 | 要移除 |

**「優惠價即時更新」在菜單卡片上是新功能，不是保留既有行為。** catalog API 完全不掛活動：

```text
GET /api/v1/catalog/items → 198 個品項，0 個帶 promo_price 或 effective_price
欄位：aliases, availability_note, category, description, id, image, name,
      nutrition, prep_time_minutes, price, price_note, retired
```

優惠價目前只在**進購物車之後**才由 checkout pricing 算出來。菜單卡片從來沒顯示過優惠價。

**目前有一個 active 活動**：`cmp_fddab722…`，品項 `MCD034`，六個位置全開。

### 工作拆解

1. `ALLOWED_PLACEMENTS`（`modules/promotion/application.py:240`）縮成四個
2. catalog API 掛上生效中的活動價（新功能）
3. kiosk 菜單卡片與餐點詳情渲染優惠價（新功能）
4. Admin 顯示位置改成四個選項
5. Admin 內嵌預覽（**先給樣張，經同意再實作**）
6. 既有活動的 `placements` 含 `recommendation`／`voice` 的資料處理方式要決定

---

## 四、系統性發現：九個缺陷，一個病根

這次修的每一個問題都屬於同兩類：

**寫入端沒有被接上**

- `record_final_checkout` — 寫 `session_logs`，**零呼叫端**
- `build_order_attributions` — 寫歸因，**零生產呼叫端**
- `list_orders_scoped` — 讀 `orders`，但**沒有人寫那張表**（真訂單在 `confirmed_orders`）

**SQLite 什麼都收、PostgreSQL 不收**

- outbox `event_id`：`veo_<hex>` 寫進 `uuid` 欄
- `has_transcript`：smallint 寫進 `boolean` 欄
- `UUID(UUID(...))`：psycopg 回物件、SQLite 回字串
- backfill 崩潰後 run key 卡在 `running`，之後永遠回報「已完成」
- backfill 與投影在啟動時並行競態
- 漏斗階段名在 envelope 而非 payload，直接數 log 永遠得 0

**全部九個在 SQLite 上測不出來，整個測試套件預設跑 SQLite。**

### 建議（未執行，不在當時的清單裡）

加一條架構規則：**凡是有 `PostgresXxxStore` 的模組，至少要有一項 `@pytest.mark.postgres` 的寫入路徑測試**，用 `tests/test_architecture_boundaries.py` 那種靜態檢查強制，而不是靠記得。

---

## 五、驗證指令（照這個跑才算綠）

```bash
PW=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)

# SQLite
docker compose --env-file .env -f docker/compose.yaml --profile test run --rm --no-deps test pytest -q

# PostgreSQL（很多缺陷只在這裡現形）
docker run --rm --network project-2026_default -v "$PWD/UI_API":/app/UI_API -w /app/UI_API \
  -e APP_ENV=test -e DATABASE_BACKEND=postgresql \
  -e DATABASE_URL="postgresql://project_2026:${PW}@postgres:5432/project_2026" \
  -e DATABASE_TOPOLOGY=single -e ENABLE_NGROK=false -e ENABLE_DIAGNOSTIC_ROUTES=false \
  -e RUNTIME_DATA_ROOT=/tmp/project-2026-test-runtime -e PYTHONDONTWRITEBYTECODE=1 \
  project-2026:test pytest -q -p no:cacheprovider --no-header

# mypy / ruff
docker compose --env-file .env -f docker/compose.yaml --profile test run --rm --no-deps -w /app/UI_API test mypy
docker run --rm -u "$(id -u):$(id -g)" -e RUFF_CACHE_DIR=/tmp/rcb -v "$PWD/UI_API":/w -w /w \
  project-2026:test sh -c "ruff check . && ruff format --check ."

# 前端 —— 一定要看 exit code
cd UI_API/frontend && docker run --rm -v "$PWD":/w -w /w -u "$(id -u):$(id -g)" -e HOME=/tmp \
  node:24-alpine sh -c 'npx tsc -p tsconfig.json; echo "typecheck exit=$?"; npx vitest run'
```

**最後那一行的 `exit=$?` 是有代價的教訓。** 2026-08-14 我把 `npx tsc` 的輸出接到 `tail -2` 再 grep `error TS`，錯誤在 grep 看到之前就被截掉了，於是連續兩次把 61 個型別錯誤回報成「乾淨」，CI 才擋下來。**判斷成功要看 exit code，不要看輸出長什麼樣子。**

### 開發環境的兩個坑

**測試映像會把原始碼烤進去。** 改完程式碼要嘛重建 `--profile test build test`，要嘛用 `docker run -v "$PWD/UI_API":/app/UI_API` 掛載執行——後者快得多（約一秒 vs 一分鐘），做變異驗證時特別有用。注意 `project_analyst/` 那類 repo 根目錄的東西不在 `UI_API` 底下，掛載時要另外處理。

**GPU 會從執行中的容器消失。** Ollama 不會因此失敗，它會靜默掉回 CPU：排程器照樣回報 23 GiB CUDA 記憶體，`ggml_cuda_init` 卻說找不到裝置。判斷是否真的在 GPU 上，只有 `offloaded N/N layers to GPU` 這一行算數。`compose.ai.yaml` 的 healthcheck 現在每輪都跑 `nvidia-smi -L`，就是為了讓下一次直接現形。
