# RAG Documents

`UI_API/rag_documents/` 保存 RAG 知識庫的原始來源。Admin 可觸發清空/重建流程；此目錄內容應可版本化、審核與重建。

## 重要規則

後端會略過本 `README.md`，因此本文件只做維護說明，不進入 Chroma。

支援格式：

- `.txt`
- `.json`
- `.csv`
- `.md` / `.markdown`

為避免工程文件與知識內容混雜：

- FAQ、政策、菜單說明優先使用 TXT。
- 活動、優惠與需要機器驗證的內容優先使用 JSON/CSV。
- 工程架構、Roadmap、ADR 與治理文件只放 Repository `docs/`。

## 目錄

```text
rag_documents/
├── faq/
├── menu/
├── nutrition/
├── promotions/
└── store_policy/
```

## 內容規則

- 每份內容需有明確 owner、來源與適用範圍。
- 不發布未確認的價格、折扣、優惠、營業時間或過敏原資訊。
- 活動/優惠使用結構化欄位，包含穩定 ID、目標品項/分類、條件、期間、狀態與時區。
- AI 回覆仍需經菜單、活動與供應狀態白名單驗證。
- 不放 Secret、真實會員資料、未授權素材或不必要 PII。
- 商用環境需建立版本、review、publish、rebuild result 與 rollback 流程。

## 重建

1. 開啟 Admin。
2. 進入 `RAG 知識庫`。
3. 執行重建。
4. 確認文件數、索引版本、錯誤、耗時與抽樣查詢結果。

RAG 商用 Gate 見 [`docs/COMMERCIAL_GOVERNANCE.md`](../../docs/COMMERCIAL_GOVERNANCE.md)。
