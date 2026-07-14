# UI_API Backend

`UI_API/backend/` 是 FastAPI transport、application workflows、資料 adapters、realtime、可靠 worker 與啟動組裝所在處。

架構是 Transitional Modular Monolith，不是已完成的 domain modularization。

## 結構與責任

```text
backend/
├── app_factory.py      # FastAPI、middleware、health、static、routes
├── api/                # route registry、/api/v1 DTO/error/組裝
├── bootstrap/          # startup、dev servers、process/module registry
├── core/               # constants、async helper
├── models/             # typed domain/contract models
├── modules/identity/   # 目前唯一已抽離的 domain Application API
├── routes/             # HTTP/WebSocket transport
├── services/           # use cases、policies、legacy application layer
├── repositories/       # JSON/PostgreSQL/Redis adapters
├── integrations/       # Payment/POS 外部邊界；目前 manual-only
├── realtime/           # WebSocket connection manager/event bus
├── schemas/            # PostgreSQL schema/migrations
├── scripts/            # trusted maintenance/worker CLIs
├── prompts/            # 預設 prompts
├── shared/             # 跨後端錯誤型別
└── utils/              # 通用解析、auth、檔案與 scope helper
```

## 目前依賴方向

```text
FastAPI route
  ├─→ modules/identity/application.py → internal policy/adapter
  └─→ service → repository/integration
```

目標方向是 `Route → Module Application API → Domain/Port → Adapter`。`bootstrap/module_registry.py` 已列出未來 domain routers，但除了 Identity 外尚未有對應 `modules/<domain>/api.py`；不可把候選清單視為已實作模組。

已知過渡債：

- `services/admin_identity_service.py`、`admin_access_service.py`、`admin_authorization_service.py` 是 Identity compatibility shims。
- `routes/v1_routes.py` 同時提供多 domain typed read/write endpoints，仍直接呼叫 service/repository。
- JSON 與 PostgreSQL 雙路徑仍共存；只有 development/test 可使用 JSON 相容模式。

## 執行與安全邊界

- `app_factory.create_app()` 執行 commercial startup validation、logging、CORS、安全 headers、request/trace correlation、`/live`、`/ready` 與 route 註冊。
- demo/test/debug routes 由 registry feature flags 控制；商用環境預設 fail closed。
- Admin session、Device session/credential、RBAC 與 tenant/store/device scope 由 server 強制。
- 阻塞資料庫、模型與 I/O 應離開 async event loop。
- Worker 由 `scripts/run_worker.py` 獨立執行 durable job/outbox claim、retry、visibility timeout 與 DLQ。
- AI、RAG、STT/TTS、Emotion provider 是可降級能力，不是 checkout authority。

## 主要功能群

- Identity/RBAC、Device identity、Member UUID/PII、Session。
- Menu/availability、promotion、checkout pricing、Order aggregate、manual payment/POS。
- Recommendation context/engine/events/feedback/experiments/governance。
- RAG document/review/publish/rollback、offer guard、alerts、object storage metadata。
- Voice/STT/TTS、multimodal evidence、barrier/intervention pipeline。
- Fleet commands、analytics pipeline、audit、observability、health。
- Reliable worker、transactional outbox、Redis shared infrastructure。

子層文件：

- [Routes](routes/README.md)
- [Services](services/README.md)
- [Repositories](repositories/README.md)
- [Schemas/Migrations](schemas/README.md)
- [Maintenance scripts](scripts/README.md)
