# UI_API Backend

`UI_API/backend/` 是核心後端，負責 API、application workflow、資料存取、WebSocket、啟動流程與共用基礎能力。

## 結構

```text
backend/
├── api/             # Router registry 與應用組裝
├── bootstrap/       # 啟動、初始化與開發 server
├── core/            # 常數、async/settings 等基礎能力
├── models/          # Dependency model
├── prompts/         # 預設 Prompt
├── realtime/        # WebSocket 與事件匯流
├── repositories/    # JSON/PostgreSQL adapter
├── routes/          # FastAPI routes
├── schemas/         # DB schema、migration、跨層 contract
├── scripts/         # Migration/validation 工具
├── services/        # Application service 與業務規則
└── utils/           # 通用 helper
```

## 依賴方向

```text
routes → services → repositories
```

演進目標：

```text
Route/API
   ↓
Application Service
   ↓
Domain Policy
   ↓
Repository Port
   ↓
Infrastructure Adapter
```

規則：

- Route 不直接實作複雜推薦、價格、會員或 RAG 規則。
- Service 不處理 HTTP status、Request/Response 或前端 rendering。
- Repository 不 import service/route，不決定業務策略。
- `utils` 必須保持通用，避免成為無邊界的共用雜物區。
- 外部 LLM、STT、TTS、Emotion 與儲存逐步使用 Port/Adapter。
- 新公開 API 優先使用 `/api/v1/*` 與 Pydantic schema；現有 `/api/*` 保持相容。

## 主要能力

- 會員、偏好、Session 與訂單歷史。
- 菜單、活動、供應狀態、Checkout pricing。
- AI 推薦、推薦上下文、事件與回饋。
- RAG 文件、審核、offer guard 與告警。
- 語音點餐、STT、TTS。
- Emotion-LLaMA / R1-Omni provider。
- WebSocket、健康檢查、audit 與 observability。
- PostgreSQL migration、備份與還原支援。

## 驗證

依變更執行目標測試；需要完整回歸時：

```bash
cd UI_API
MEMBER_STORAGE_BACKEND=json DATABASE_URL= pytest -q tests
```

Core/API/utils 的 static check 範圍以 `.github/workflows/ci.yml` 為準。

## 文件

- [整體架構](../../docs/ARCHITECTURE.md)
- [商業化治理](../../docs/COMMERCIAL_GOVERNANCE.md)
- [後續模組](../../docs/FUTURE_MODULES.md)
