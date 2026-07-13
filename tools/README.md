# Tools

`tools/` 保存非 production path 的本機 Demo、一次性維運與開發輔助工具。`main.py` 與 production routes 不得依賴此目錄。

## 目前工具

| 工具 | 用途 |
| --- | --- |
| `demo_passive_voice.py` | 被動語音關鍵詞偵測 Web Demo |
| `import_menu_to_rag.py` | 將菜單品項批次匯入 RAG 的維運工具 |

## 使用

從 Repository 根目錄執行：

```bash
conda run -n emotion_ui python tools/demo_passive_voice.py
conda run -n emotion_ui python tools/import_menu_to_rag.py
```

執行前先閱讀工具參數與輸出路徑；涉及資料寫入時先在測試資料執行。

## 維護規則

- 只放本機 Demo、一次性維運、資料檢查或開發輔助工具。
- 不放正式 API route、production 必要 migration 或長期 background service。
- 工具不得預設讀取/輸出真實 Secret、完整 PII 或 production dump。
- 寫入檔案/資料庫的工具應支援 dry-run 或明確確認（高風險時）。
- 可重複的正式流程應移到 `UI_API/backend/scripts/`、service 或 Worker，並補測試、log、權限與失敗恢復。
- 工具若已無用途，先確認無文件、CI、script 或操作流程引用再刪除。
