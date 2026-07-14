# Smart Ordering Kiosk 智慧自助點餐系統

Project_2026 是一套整合 Kiosk 自助點餐、Admin 營運後台、會員個人化、AI 推薦、語音互動、RAG 與多模態情緒分析的智慧點餐平台。

目前採 **Modular Monolith First**：核心應用位於 `UI_API/`，以 FastAPI 提供 API、WebSocket 與現行前端入口；`Emotion-LLaMA/` 與 `R1-Omni/` 為可替換的外部模型執行單元。

## 主要能力

- Kiosk：菜單、購物車、會員登入、活動、AI 推薦、語音點餐、結帳與互動事件。
- Admin：營運統計、會員、活動、供應狀態、推薦事件、RAG、模型設定與健康檢查。
- Backend：routes → services → repositories 分層、JSON/PostgreSQL 儲存、WebSocket、audit 與 observability。
- AI：Ollama/Gemini、STT/TTS、RAG、Emotion-LLaMA/R1-Omni provider。
- 工程基線：GitHub Actions、Ruff、mypy、pytest、TypeScript typecheck 與 Shell syntax check。

## Repository 結構

```text
Project_2026/
├── UI_API/           # FastAPI、Kiosk、Admin、RAG、資料與測試
├── Emotion-LLaMA/    # 可選情緒分析服務
├── R1-Omni/          # 可選多模態情緒分析服務
├── scripts/          # 本機啟動、PostgreSQL 備份與還原
├── tools/            # 非 production path 的開發與維運工具
├── docs/             # 架構決策、商用治理與後續模組規劃
├── AGENTS.md         # 人員與 Codex 的工程協作規則
└── .github/workflows/ci.yml
```

## 快速開始（Local-first，不需要 Docker）

本專案以**本機 / 區域網路原生 Process** 為主要執行方式。Docker 非必要；歷史 Docker 檔案僅存於 `docs/archive/docker/`。

### 1. 建立環境

```bash
cd UI_API
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp ../.env.example ../.env
```

依本機環境調整 `.env`，不要提交真實 Secret。JSON 開發模式可維持 `MEMBER_STORAGE_BACKEND=json`；商用本機再接 PostgreSQL。

### 2. 啟動核心應用

```bash
cd UI_API
python main.py
# 另開終端（PostgreSQL 模式需要）：
python backend/scripts/run_worker.py
```

預設入口：

```text
Kiosk: http://127.0.0.1:9000/kiosk
Admin: http://127.0.0.1:9001/admin
```

可選模型服務：

```bash
bash scripts/start_emotion_llama.sh
bash scripts/start_r1_omni.sh
```

詳細： [docs/LOCAL_DEPLOYMENT.md](docs/LOCAL_DEPLOYMENT.md)、[docs/LOCAL_RUNTIME_INVENTORY.md](docs/LOCAL_RUNTIME_INVENTORY.md)。

## 驗證

Backend：

```bash
cd UI_API
MEMBER_STORAGE_BACKEND=json DATABASE_URL= pytest -q tests
```

Frontend：

```bash
cd UI_API/frontend
npm ci --ignore-scripts
npm run typecheck
npm run syntax
```

Shell：

```bash
bash -n scripts/start_emotion_llama.sh
bash -n scripts/start_r1_omni.sh
bash -n scripts/lib_postgres.sh
bash -n scripts/backup_postgres.sh
bash -n scripts/restore_postgres.sh
```

完整 CI 基線見 `.github/workflows/ci.yml`。

## 文件導覽

- [工程協作規則](AGENTS.md)
- [文件中心](docs/README.md)
- [目前與目標架構](docs/ARCHITECTURE.md)
- [架構決策 ADR](docs/adr/README.md)
- [商業化治理](docs/COMMERCIAL_GOVERNANCE.md)
- [後續模組規劃](docs/FUTURE_MODULES.md)
- [UI_API](UI_API/README.md)
- [Backend](UI_API/backend/README.md)
- [Frontend](UI_API/frontend/README.md)
- [Tests](UI_API/tests/README.md)
- [RAG documents](UI_API/rag_documents/README.md)
- [Scripts](scripts/README.md)
- [Tools](tools/README.md)
- [Emotion-LLaMA](Emotion-LLaMA/README.md)
- [R1-Omni](R1-Omni/README.md)

## 商用化原則

- 保持 Modular Monolith，先建立清楚模組邊界，再依實際 scaling 與故障隔離需求拆服務。
- 正式環境使用 PostgreSQL、受管 Secret、明確 CORS allowlist，並關閉 demo/test/debug routes。
- Admin 身分、角色權限、多租戶/多門市、Kiosk device credential、PII 保護與 migration 需依 Roadmap 漸進導入。
- UI_API、PostgreSQL、Redis/Worker 與大型 AI 模型應使用獨立 process；本機以原生啟動為主，不強制容器。
- 商用前逐項確認模型、資料集、圖片、品牌素材與第三方套件授權。

具體門檻見 [docs/COMMERCIAL_GOVERNANCE.md](docs/COMMERCIAL_GOVERNANCE.md)。
