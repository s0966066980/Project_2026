# Project_2026 文件中心

`docs/` 保存跨模組、需要長期維護與版本追蹤的工程文件。模組的即時操作方式仍放在各自的 `README.md`。

## 文件導覽

| 文件 | 用途 | 何時更新 |
| --- | --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 目前架構、目標架構、責任邊界與演進原則 | 架構或部署邊界改變時 |
| [adr/README.md](adr/README.md) | Architecture Decision Record 索引與新增規則 | 新增或取代架構決策時 |
| [COMMERCIAL_GOVERNANCE.md](COMMERCIAL_GOVERNANCE.md) | 商用上線、安全、資料、AI、營運與發布治理 | 商用門檻或責任改變時 |
| [POSTGRESQL_MIGRATIONS.md](POSTGRESQL_MIGRATIONS.md) | PostgreSQL migration、CI、backup 與 recovery runbook | Migration framework 或維運流程改變時 |
| [FUTURE_MODULES.md](FUTURE_MODULES.md) | 後續模組、優先級、依賴與完成條件 | Roadmap 優先級或狀態改變時 |

## 文件責任

- 根目錄 `README.md`：專案入口、快速啟動、驗證命令與文件連結。
- 根目錄 `AGENTS.md`：人員與 Codex 的執行規則；保持短、明確、可直接操作。
- 模組 `README.md`：只描述該模組的責任、入口、邊界與最小驗證方式。
- `ARCHITECTURE.md`：描述現在與目標，不記錄每次小型重構。
- `adr/`：保存已接受或被取代的長期架構決策；已接受 ADR 不直接改寫結論。
- `COMMERCIAL_GOVERNANCE.md`：定義可商用與可發布的門檻。
- `FUTURE_MODULES.md`：保存尚未完成的工作，不把已完成項目長期留在待辦區。

## 維護規則

1. 文件以繁體中文為主，程式名稱、API、路徑與標準術語保留英文。
2. 只建立有明確 owner 與更新觸發條件的文件，避免新增零散分析、暫時性 review 或重複 roadmap。
3. 程式行為改變時，同一變更同步更新受影響的 README、架構文件或 ADR。
4. README 描述目前事實；未實作內容只放在 `FUTURE_MODULES.md`。
5. 重大且難以回復的決策使用 ADR；一般重構與檔名調整不需要 ADR。
6. RAG 知識內容放在 `UI_API/rag_documents/`，不得混入本目錄的工程治理文件。
