# Tools

`tools/` 保存非 production path 的本機 demo、一次性維運與分析工具。FastAPI routes、正式 migrations 與 worker 不得依賴此目錄。

## 目前工具

| 工具 | 用途 | 主要副作用 |
| --- | --- | --- |
| `demo_passive_voice.py` | 被動語音關鍵詞偵測 Web demo | 啟動本機 demo server/音訊處理 |
| `import_menu_to_rag.py` | 將菜單項目匯入 RAG | 寫入設定的 RAG collection |

## 使用

Tools 不構成正式 application runtime，也不需要主機 Conda。需要時，從 Repository 根目錄將 `tools/` 唯讀掛載進 AI app image：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  run --rm \
  -v "$PWD/tools:/app/tools:ro" \
  app python /app/tools/import_menu_to_rag.py
```

被動語音 demo 需要額外映射其開發 port：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  run --rm \
  -p 127.0.0.1:8088:8088 \
  -v "$PWD/tools:/app/tools:ro" \
  app python /app/tools/demo_passive_voice.py
```

`demo_passive_voice.py` 會啟動 demo server；`import_menu_to_rag.py` 沒有 dry-run 且會直接寫入目前設定的 RAG collection，執行前必須確認環境與資料來源。這些工具不是 Kiosk/Admin 一鍵 stack 的必要組件。
