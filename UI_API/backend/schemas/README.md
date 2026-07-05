# schemas 模組說明

`schemas/` 放置資料庫 schema 與跨層資料結構。

## 目前內容

- `membership_postgres.sql`：會員、推薦事件、供應狀態與 audit 相關 PostgreSQL schema。

## 維護規則

- 新資料表需有明確主鍵、索引與 created / updated 欄位。
- migration 應可重複執行或有版本保護。
- API request / response 若逐步擴大，建議新增 Python schema module 管理。
