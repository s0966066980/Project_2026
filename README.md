# Project_2026 — Smart Ordering Kiosk

單店本地端 Kiosk Pilot：Modular Monolith，本機 / LAN 原生 process，**不需要 Docker**。

## Overview

- **Kiosk**：菜單、購物車、會員、推薦、語音、結帳
- **Admin**：登入、設定、供應、活動、訂單、RAG、裝置
- **Backend**：`/api/v1` → Module Application API → Port → PostgreSQL / Local adapters
- **Optional AI**：Ollama、Emotion-LLaMA / R1-Omni（不阻擋 Checkout）

## Quick Start (local-pilot)

```bash
cd UI_API
python3 -m venv .venv && source .venv/bin/activate
bash ../scripts/local/setup.sh --profile local-pilot
cp ../config/profiles/local-pilot.env.example ../.env   # edit secrets locally
# PostgreSQL running; set DATABASE_URL in .env
export ADMIN_BOOTSTRAP_PASSWORD='...'   # never commit
python backend/scripts/bootstrap_local_pilot.py --tenant-name "Owner" --store-name "Store A"
APP_PROFILE=local-pilot bash ../scripts/local/start.sh
```

```text
Kiosk: http://127.0.0.1:9000/kiosk
Admin: http://127.0.0.1:9001/admin
```

## Architecture Summary

```text
Frontend (v1Client)
  → FastAPI /api/v1 Module Routers
    → Module Application API
      → Domain / Ports
        → PostgreSQL | Local Object Storage | Optional Providers
```

PostgreSQL is the **only** commercial data source for `local-pilot`.

## Tests

```bash
bash scripts/local/test_fast.sh
bash scripts/local/test_full.sh
```

## Core Docs

- [AGENTS.md](AGENTS.md) — collaboration & architecture rules
- [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — current status
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DATABASE.md](docs/DATABASE.md)
- [docs/API_MODULES.md](docs/API_MODULES.md)
- [docs/LOCAL_OPERATIONS.md](docs/LOCAL_OPERATIONS.md)
- [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md)
