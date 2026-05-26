# Voice × Emotion × RAG 修復設計文件
**日期**：2026-05-26  
**範圍**：五個問題修復 — 語音 bug、AI 推播、emotion 整合、RAG 重建

## 問題清單
1. 語音模式時 emotion 未執行
2. 語音模式無 AI 回覆（model name 錯誤）
3. AI 推播間隔改為 10 秒 / 顯示 5 秒
4. Emotion-LLaMA 重寫：語音開啟時觸發，結果傳 Ollama，結帳時存 RAG
5. RAG 清理並重新建立（PDF + 四類知識）

## 方案選擇：方案 A（輕量快照整合）
- 語音按鈕按下時擷取 1 秒 emotion snapshot，不阻塞錄音流程
- emotion_cache 已有資料後，voice service 自動讀取（現有邏輯正確）
- sessionEmotionLog 累積，結帳時批次寫 RAG

## 改動檔案
| 檔案 | 說明 |
|---|---|
| `config.py` | VOICE_ASSIST_MODEL 預設改 qwen3.5:4b，RECOMMEND_INTERVAL_SEC 改 10 |
| `services/voice_assist_service.py` | model fallback，emotion hint 強化 |
| `routes/core_routes.py` | checkout 接收 emotion_session_log，觸發 RAG 寫入 |
| `static/app.js` | emotion snapshot on voice start，sessionEmotionLog，interval 改 10 |
| `seeds/rag_knowledge.py` | 四類知識常數 |
| `main.py` | 啟動時初始化 RAG seeds + PDF |
