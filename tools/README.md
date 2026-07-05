# tools 模組說明

`tools/` 存放非 production path 的本機 demo 與維運工具。這些工具不應由 `main.py` 或 production routes import。

## 主要工具

| 工具 | 用途 |
| --- | --- |
| `demo_passive_voice.py` | 被動語音關鍵詞偵測 Web Demo。 |
| `import_menu_to_rag.py` | 將菜單品項批次匯入 RAG 的維運工具。 |

## 使用方式

從專案根目錄執行：

```bash
conda run -n emotion_ui python tools/demo_passive_voice.py
conda run -n emotion_ui python tools/import_menu_to_rag.py
```

## 維護規則

- 只放本機 demo、一次性維運或開發輔助工具。
- 不放正式 API route。
- 不放 production 必須執行的 migration。
- 若工具變成正式流程，應移到 `UI_API/backend/scripts/` 或 service 層並補測試。
