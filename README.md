# Smart Ordering POS 智慧點餐平台

這是一套面向自助點餐機與門市後台的智慧點餐 / POS 系統。專案整合 FastAPI 後端、瀏覽器 POS 與 Admin 介面、語音點餐、AI 推播推薦、會員個人化、RAG 知識庫，以及可選的多模態情緒分析服務。

主要應用程式位於 `UI_API/`。`Emotion-LLaMA/` 與 `R1-Omni/` 是可選的情緒 / 多模態模型服務，用於進階分析流程。

## 主要功能

- 自助點餐 POS：菜單瀏覽、購物車、結帳、付款倒數、訂單完成畫面。
- Admin 後台：系統設定、統計、紀錄、測試、會員管理、RAG 知識庫管理。
- AI 推播推薦：依據購物車、會員偏好、熱門品項與設定產生顧客可見推薦。
- 語音點餐：支援 STT、LLM、TTS 的語音助理流程。
- 會員系統：手機登入 / 註冊、常點、歷史訂單、個人化推薦。
- 訂單狀態追蹤：區分已完成訂單與取消 / 回首頁造成的未完成訂單。
- 互動事件追蹤：紀錄猶豫、付款卡住、返回、取消、求助等事件。
- RAG 知識庫：支援 FAQ、活動、門市政策、營養過敏原與菜單補充文件。
- WebSocket 即時事件推送。
- 可選 Emotion-LLaMA / R1-Omni 情緒分析整合。
- 透過 `.env` 與 `learning_data/settings.json` 調整執行設定。

## 專案結構

```text
.
├── UI_API/
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 環境變數與 runtime 設定
│   ├── backend/
│   │   ├── api/                    # Router 註冊
│   │   ├── bootstrap/              # 啟動流程與 server helper
│   │   ├── core/                   # 共用常數與基礎工具
│   │   ├── models/                 # 後端資料模型與依賴型別
│   │   ├── prompts/                # 預設 AI prompt
│   │   ├── realtime/               # WebSocket 與事件匯流排
│   │   ├── repositories/           # JSON 檔案資料存取層
│   │   ├── routes/                 # FastAPI routes
│   │   ├── services/               # 業務邏輯、AI、RAG、會員服務
│   │   └── utils/                  # 共用工具
│   ├── frontend/
│   │   ├── admin/                  # Admin 後台
│   │   ├── pos/                    # POS 點餐介面
│   │   ├── shared/                 # 前端共用 API client / UI helper
│   │   ├── mcd_categories/         # 分類圖片
│   │   └── menu_images/            # 菜單圖片
│   ├── learning_data/              # runtime 資料，不提交實際內容
│   ├── menu_data/                  # 菜單 JSON
│   ├── rag_documents/              # RAG 原始知識文件，提交 Git
│   └── tests/                      # 後端測試
├── Emotion-LLaMA/                  # 可選情緒分析服務
├── R1-Omni/                        # 可選多模態情緒分析服務
├── scripts/                        # 本機啟動腳本
└── MEMBERSHIP_RECOMMENDATION_IMPROVEMENTS.md
```

## 技術棧

### 後端

- Python 3
- FastAPI
- Uvicorn
- WebSocket
- JSON 檔案型 repository
- ChromaDB / LangChain RAG 整合
- Ollama local LLM
- Google GenAI 可選整合

### 前端

- HTML / CSS / Vanilla JavaScript ES Modules
- POS 介面部分使用 Tailwind CDN
- Font Awesome icon
- Browser Media APIs，用於麥克風與影像擷取

### AI 與媒體

- Ollama 本機模型服務
- Faster Whisper 或 OpenAI-compatible STT
- Edge TTS、MeloTTS 或 OpenAI-compatible TTS
- Emotion-LLaMA，可選
- R1-Omni，可選

## 安裝

```bash
git clone <repository-url>
cd Project_2026

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r UI_API/requirements.txt
```

如果需要使用 `Emotion-LLaMA/` 或 `R1-Omni/`，請依照各模型服務的需求另外建立環境並安裝依賴。

## 環境變數

需要本機覆寫設定時，在 `UI_API/` 建立 `.env`：

```bash
cd UI_API
cp .env.example .env  # 如果存在範例檔
```

常用設定：

| 變數 | 說明 | 預設 |
| --- | --- | --- |
| `APP_HOST` | FastAPI host | `0.0.0.0` |
| `APP_PORT` | POS / API port | `8000` |
| `ADMIN_PORT` | Admin port | `8001` |
| `OLLAMA_API_URL` | Ollama generate API | `http://localhost:11434/api/generate` |
| `GEMINI_API_KEY` | Gemini API key | 空字串 |
| `EMOTION_LLAMA_GRADIO_URL` | Emotion-LLaMA 服務 URL | `http://127.0.0.1:7889` |
| `R1_OMNI_GRADIO_URL` | R1-Omni 服務 URL | `http://127.0.0.1:7890` |
| `ENABLE_NGROK` | 是否啟動 ngrok | `true` |
| `POS_DEMO_TOKEN` | POS demo token | 空字串 |
| `ADMIN_DEMO_TOKEN` | Admin demo token | 空字串 |
| `WS_DEMO_TOKEN` | WebSocket demo token | 空字串 |
| `CORS_ORIGINS` | CORS 允許來源 | localhost 預設值 |

runtime 設定也會保存在 `UI_API/learning_data/settings.json`，可透過 Admin 後台或設定 API 更新。`learning_data/` 是執行期資料，不應提交實際內容。

## RAG 知識庫

RAG 原始文件放在：

```text
UI_API/rag_documents/
```

這些文件應提交 Git。執行時產生的 Chroma 向量資料庫位於 `UI_API/learning_data/chroma_rag/`，不應手動編輯或提交。

建議格式：

- Markdown：FAQ、政策、菜單補充、客服 SOP。
- JSON：活動、會員優惠、結構化規則。
- CSV：營養、過敏原、價格、門市政策表格。

Admin 操作：

1. 開啟 Admin。
2. 進入 `RAG 知識庫`。
3. 使用 `新增 / 更新 RAG 文本` 新增單筆內容。
4. 使用 `清空 Chroma 並重新讀取 RAG 文件` 從 `UI_API/rag_documents/` 重建向量庫。

## 本機啟動

啟動主應用程式：

```bash
cd UI_API
python main.py
```

預設網址依 `APP_PORT` 與 `ADMIN_PORT` 而定：

- POS：`http://127.0.0.1:8000/pos`
- Admin：`http://127.0.0.1:8001/admin`

也可以使用啟動腳本同時啟動模型服務與 UI：

```bash
bash scripts/start_emotion_llama.sh
bash scripts/start_r1_omni.sh
```

腳本預設使用 `APP_PORT=9000`、`ADMIN_PORT=9001`，並會嘗試自動開啟 POS / Admin。可用環境變數覆寫：

```bash
APP_PORT=8000 ADMIN_PORT=8001 OPEN_BROWSER=false bash scripts/start_emotion_llama.sh
```

## 測試與檢查

執行後端測試：

```bash
cd UI_API
python -m pytest tests
```

執行 Python / JavaScript 靜態檢查：

```bash
cd UI_API
python -m py_compile main.py $(find backend -type f -name '*.py' -not -path '*/__pycache__/*')
find frontend -type f -name '*.js' -print | sort | xargs -n 1 node --check
```

建議測試範圍：

- route 註冊與 API response contract
- 會員登入、註冊、常點、歷史訂單
- 結帳與 session log
- AI 推播 fallback
- RAG 空資料與已建庫行為
- 語音點餐錯誤處理
- 互動事件與介入觸發

## 部署建議

1. 建立 Python runtime，安裝 `UI_API/requirements.txt`。
2. 設定 `.env` 與 `learning_data/settings.json`。
3. 使用 `systemd`、`supervisord` 或平台服務管理 Uvicorn。
4. 使用 Nginx / Caddy 等 reverse proxy 提供 TLS、壓縮與公開路由。
5. 需要時將 Ollama、Emotion-LLaMA、R1-Omni 等模型服務獨立部署。
6. 持久化 `UI_API/learning_data/` 與向量資料庫。
7. Admin 應使用 token 與網路層控管存取。

Uvicorn 範例：

```bash
cd UI_API
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 注意事項

- GitHub 版本只應包含 source code、測試、文件與可重建的 RAG 原始文件。
- `UI_API/learning_data/`、模型權重、cache、log、`.env` 都不應提交。
- 會員登入目前以手機號碼識別，正式商用前應加入 OTP 或 PIN 等驗證機制。
- `MEMBERSHIP_RECOMMENDATION_IMPROVEMENTS.md` 記錄會員推薦與語音個人化的後續改進規劃。
