# repositories 模組說明

`repositories/` 是資料存取層，負責隔離 JSON 檔案與 PostgreSQL。

## 主要 repository

- `member_repository.py`：會員資料。
- `member_session_repository.py`：會員 session。
- `recommendation_event_repository.py`：推薦事件。
- `availability_repository.py`：供應狀態。
- `admin_audit_repository.py`：Admin 操作稽核。
- `menu_repository.py`：菜單資料。
- `session_repository.py`：點餐 session。
- `interaction_event_repository.py`：互動事件。
- `postgres_utils.py`：PostgreSQL 共用工具。

## 維護規則

- repository 不應 import route。
- repository 不應承擔推薦或會員商業決策。
- JSON backend 可作為開發模式。
- 商用資料應走 PostgreSQL。
- 新資料表應同步補 migration、repository 與測試。
