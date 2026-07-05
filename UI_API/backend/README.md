# UI_API backend 模組說明

`backend/` 是 UI_API 的後端核心，負責 API、業務邏輯、資料存取、WebSocket、啟動流程與共用工具。

## 主要結構

```text
backend/
├── api/             # router 組裝
├── bootstrap/       # 啟動流程
├── core/            # 共用常數與基礎工具
├── models/          # dependency model
├── prompts/         # 預設 prompt
├── realtime/        # WebSocket 與事件匯流排
├── repositories/    # JSON / PostgreSQL 資料存取
├── routes/          # FastAPI routes
├── schemas/         # SQL schema 與資料結構
├── scripts/         # migration / validation scripts
├── services/        # 業務邏輯
└── utils/           # 共用 helper
```

## 分層規則

```text
routes -> services -> repositories
```

- routes 只處理 HTTP、權限、輸入輸出。
- services 負責業務規則與流程。
- repositories 負責資料讀寫。
- utils 不應依賴 routes/services。
- repositories 不應反向 import services。

## 主要功能

- 會員登入、註冊、偏好、歷史訂單。
- AI 推薦、推薦上下文、推薦事件。
- RAG 文件管理、審核、offer guard。
- 語音點餐、STT、TTS。
- 情緒分析 provider。
- 供應狀態、活動、健康檢查。
- PostgreSQL migration 與備份支援。

## 維護重點

- 新 API 應先定義 route，再把核心邏輯放 service。
- 新資料來源應建立 repository，不要在 service 直接讀寫檔案。
- 新跨模組資料結構應放在 schemas 或明確 service response。
