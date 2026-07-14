# RAG Documents

`UI_API/rag_documents/` 是可版本化的 RAG 原始來源。Admin 的 validate/rebuild 與 review/publish 流程會使用此目錄；本 `README.md` 會被 ingestion 明確略過。

> 實作盤點：2026-07-14。系統同時存在 filesystem review compatibility flow 與 PostgreSQL/object-storage durable governance flow，尚在漸進切換。

## 支援格式與目錄

支援 `.txt`、`.json`、`.csv`、`.md`、`.markdown`。目前內容分類：

```text
rag_documents/
├── faq/
├── menu/
├── nutrition/
├── promotions/
└── store_policy/
```

- FAQ、政策、菜單說明優先使用 TXT/Markdown。
- 價格、期間、條件與 target 需要機器驗證的活動優先使用 JSON/CSV。
- 工程架構、roadmap 與開發工作規則不應放入本目錄，避免進入顧客知識庫。

## Governance 流程

Legacy Admin routes 提供 documents/reviews/alerts、validate、preview、rebuild 與 promotions。Typed `/api/v1/rag/documents` 提供 draft → review → publish/rollback contract；durable metadata 由 migrations `0010`/`0011` 保存，binary/content 可透過 object reference 管理。

重建前應：

1. 驗證格式、scope、checksum 與 structured offer。
2. 修正所有 blocking errors；不要先清空現有 collection。
3. 執行 preview/rebuild，確認 imported/deleted/failed counts。
4. 抽樣查詢並檢查 alert/review/audit；失敗時保留可回復版本。

## 內容規則

- 每份內容有穩定 ID、owner、來源、tenant/store scope、版本與狀態。
- 不發布未確認的價格、折扣、營業時間、庫存或過敏原資訊。
- 活動包含 target、條件、期間、時區、enabled/status；AI 仍須經 menu/promotion/availability 白名單驗證。
- 不放 secret、真實會員資料、production dump、未授權素材或不必要 PII。
- RAG/LLM output 不是 payment、order、permission 或 promotion eligibility authority。
