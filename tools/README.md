# Tools

`tools/` 保存非 production path 的本機 demo、一次性維運與分析工具。FastAPI routes、正式 migrations 與 worker 不得依賴此目錄。

## 目前工具

| 工具 | 用途 | 主要副作用 |
| --- | --- | --- |
| `demo_passive_voice.py` | 被動語音關鍵詞偵測 Web demo | 啟動本機 demo server/音訊處理 |
| `import_menu_to_rag.py` | 將菜單項目匯入 RAG | 寫入設定的 RAG collection |
| `test_inventory.py` | 掃描 Backend/Frontend tests，分類 local-first test portfolio | 預設 stdout；可選 JSON/Markdown report |

## 使用

從 Repository 根目錄執行：

```bash
conda run -n emotion_ui python tools/demo_passive_voice.py
conda run -n emotion_ui python tools/import_menu_to_rag.py
python tools/test_inventory.py --help
```

`demo_passive_voice.py` 會直接啟動本機 server；`import_menu_to_rag.py` 沒有 dry-run 且會直接寫入目前設定的 RAG collection，執行前必須確認環境與資料來源。實際依賴可能來自 UI_API 的完整 runtime environment；不要為文件或單一分析工具重裝所有模型依賴。
