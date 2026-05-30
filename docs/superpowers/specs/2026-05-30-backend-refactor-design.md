# Backend Refactor — 語音、Emotion-LLaMA、RAG 清理與重構

**日期**：2026-05-30  
**範圍**：`UI_API/` 後端 Python 程式碼

---

## 目標

1. 刪除舊語音點餐實作，以乾淨的 STT → Ollama → TTS 架構取代，保留 Whisper，預留 RAG 插槽（TODO 註解）。
2. 刪除所有 Emotion-LLaMA 處理程式碼，建立可對接 Emotion-LLaMA 的 stub endpoint。
3. 刪除所有 RAG 實作，只在語音 prompt 組裝處留 TODO 註解。
4. 清除舊架構殘碼（recommend_cache、seeds、PDF、sample_data）。

---

## 刪除清單

### 整個檔案刪除

| 檔案 | 原因 |
|------|------|
| `services/voice_assist_service.py` | 舊語音邏輯，由新版取代 |
| `services/query_router_service.py` | 意圖路由，新版不需要 |
| `services/customer_service.py` | Emotion-LLaMA 處理層 |
| `services/emotion_risk_service.py` | Emotion-LLaMA 風險計算 |
| `services/multimodal_evidence_service.py` | Emotion-LLaMA 多模態證據 |
| `routes/multimodal_routes.py` | 多模態 pipeline 路由 |
| `rag_service.py` | ChromaDB / LangChain RAG 實作 |
| `routes/rag_routes.py` | RAG 管理 API |
| `services/rag_review_service.py` | RAG 文本審查 |
| `seeds/` 整個目錄 | RAG 種子資料（含 `rag_knowledge.py`） |
| `gemini_direct_chat.py` | 獨立測試腳本，非系統功能 |
| `mcdonalds_tw_extra_value_meals_rag.pdf` | RAG 來源 PDF |
| `sample_data/` 整個目錄 | 範例設定，非運作必要 |

---

## 局部修改

### `ai_services.py`
刪除以下 5 個函式（Emotion-LLaMA 耦合）：
- `async_get_emotion_from_llama()`
- `async_analyze_emotion_media_signals()`
- `async_prepare_emotion_video()`
- `_measure_motion_signals()`
- `_build_emotion_llama_prompt()`

保留：Whisper STT、TTS（Edge TTS）、Ollama、Gemini、`async_probe_media`、`check_emotion_llama_status`（用於 stub 狀態確認）。

### `database.py`
刪除以下 RAG 函式：
- `init_rag_system()`
- `get_rag_docs()` / `save_rag_docs()`
- `upsert_reviewed_rag_doc()`
- `delete_rag_doc()`
- `get_global_rag_context()`
- `retrieve_menu_from_rag()`
- `get_successful_experiences()` / `_build_successful_experiences()`（舊推薦系統死碼）
- `get_order_pairing_context()` / `_build_order_pairing_context()`（舊推薦系統死碼）
- `seed_rag_docs()`
- `seed_pdf_to_rag()`
- `load_pdf_chunks()`
- `save_voice_emotion_to_rag()`
- `_ensure_rag_docs_from_menu()`
- `_history_cache` 及 `_cached_history()`（RAG context 快取，隨 RAG 函式一起移除）

保留：`build_menu_item_text()`、`build_full_menu_context()`、`update_menu()`、`record_final_checkout()`、`clear_rag_storage()` 簡化為空操作或移除。

### `main.py`
- 移除 `from seeds.rag_knowledge import RAG_SEEDS`
- 移除 `_background_init_once()` 中的 PDF 匯入段與 seed 注入段
- 移除 `_background_init_once()` 中 `_init_rag()` 整段（RAG 初始化）
- 移除 `_route_dependencies()` 中的 `emotion_cache`、`emotion_semaphore`
- 移除 `multimodal_routes`、`rag_routes` 的 import 與 `include_router`
- 替換 `voice_routes` import 為新版

### `routes/core_routes.py`
移除 `recommend_cache` 相關殘碼（第 173、180、259–262 行）：
- `deps["recommend_cache"].clear()` × 2（刪除行為，否則 KeyError）
- `recommend_cache = deps.get("recommend_cache") or {}` 段落（清空邏輯）

### `routes/menu_routes.py`
移除第 26 行 `(deps.get("recommend_cache") or {}).clear()`

### `services/barrier_state_service.py`
移除以下依賴與參數：
- `from services import emotion_risk_service` import
- `infer_barrier_state()` 中的 `emotion_structured`、`media_signals`、`person_check` 參數
- 所有 `emotion_risk_service.calculate_emotion_risk()` 呼叫
- 輸出中的 `emotion_risk_score`、`emotion_risk_level`、`emotion_risk_rules`、`emotion_risk_evidence`、`media_signals` 欄位

新簽名：`infer_barrier_state(speech_text, pos_events, ui_context, risk_result) -> dict`

### `services/intervention_pipeline_service.py`
移除以下參數與相依：
- `emotion_structured`、`media_signals`、`person_check`、`multimodal_evidence` 參數
- `from services import multimodal_evidence_service` import
- `build_multimodal_evidence()` 呼叫
- 回傳值中的 `multimodal_evidence` 欄位

新簽名：
```python
async def run_intervention_pipeline(
    session_id: str,
    ui_context: dict,
    risk_result: dict | None = None,
    recent_events: list | None = None,
    speech_text: str = "",
    scenario_id: str | None = None,
    source: str = "unknown",
    publish: bool = True,
) -> dict
```

---

## 新增檔案

### `services/voice_service.py`

**流程：**
```
音訊 → Whisper STT → 取菜單 → 組 prompt
                              ↑
                    # TODO: inject RAG context
                              ↓
                         Ollama LLM
                              ↓
                  解析 ai_response + cart_actions
                              ↓
                           Edge TTS
                              ↓
       { user_text, ai_response, audio_base64,
         cart_actions, detected_lang }
```

**公開介面：**
```python
async def handle_voice(
    session_id: str,
    audio_path: str,
    ollama_semaphore,
    multi_lang: bool = True,
) -> dict
```

**回傳格式：**
```json
{
  "status": "success | error",
  "user_text": "顧客語音轉文字",
  "ai_response": "AI 回覆",
  "audio_base64": "TTS 音訊",
  "cart_actions": [{"action": "add", "id": "MCDxxx", "quantity": 1}],
  "detected_lang": "zh | en"
}
```

**RAG 插槽位置：**
在 `user_prompt` 組裝前加入：
```python
# TODO: inject RAG context here
# rag_context = rag_provider.query(user_text)
```

### `services/emotion_service.py`

Emotion-LLaMA stub，未來可直接替換實作：

```python
async def analyze(session_id: str, media_path: str) -> dict:
    # TODO: Connect to Emotion-LLaMA at config.EMOTION_LLAMA_GRADIO_URL
    return {
        "session_id": session_id,
        "emotion_label": "未偵測",
        "emotion_score": 0,
        "emotion_available": False,
        "status": "stub",
    }
```

### `routes/emotion_routes.py`（重寫）

單一 endpoint：

```
POST /api/emotion/analyze
  Body: session_id (Form), media (UploadFile)
  Response: { session_id, emotion_label, emotion_score, emotion_available, status }
```

### `routes/voice_routes.py`（重寫）

簡化為呼叫新 `voice_service.handle_voice()`，移除 emotion 參數。

---

## 保留不動

- `services/intervention_service.py`
- `services/interaction_event_service.py`
- `services/scenario_service.py`
- `services/recommendation_service.py`
- `services/ai_push_service.py`
- `repositories/` 全部
- `realtime/` 全部
- `routes/core_routes.py`（局部修改後）
- `routes/menu_routes.py`（局部修改後）
- `routes/ai_push_routes.py`
- `routes/interaction_routes.py`
- `routes/debug_routes.py`
- `routes/realtime_routes.py`
- `routes/demo_routes.py`
- `config.py`
- `utils/`
- `prompts/`

---

## 驗收標準

1. `python3 -m py_compile main.py` 以及所有 `services/`、`routes/` 下的 `.py` 通過
2. `curl http://127.0.0.1:8000/api/settings` 回傳正常
3. `POST /api/voice/assist` 可收音訊，回傳 `user_text` + `audio_base64`
4. `POST /api/emotion/analyze` 回傳 `{"status": "stub", "emotion_available": false}`
5. `recommend_cache` 相關的 KeyError 不再出現
