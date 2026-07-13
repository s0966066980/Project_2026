# services 模組說明

`services/` 是後端業務邏輯層，負責把 route 的請求轉成實際商業流程。

## 主要服務群

- 會員：`member_service.py`、`member_preference_service.py`
- 推薦：`recommendation_service.py`、`recommendation_context_service.py`、`recommendation_engine_service.py`
- 推薦事件：`recommendation_event_service.py`、`recommendation_feedback_service.py`
- RAG：`rag_provider.py`、`rag_document_service.py`、`rag_guard_service.py`、`rag_offer_service.py`
- 活動：`promotion_service.py`
- 語音：`voice_service.py`、`stt_service.py`、`tts_service.py`
- 情緒：`emotion_service.py`
- 供應狀態：`availability_service.py`
- 觀測與健康：`observability_service.py` 提供 redaction、correlation 與 metrics registry；`health_service.py` 分離 liveness/readiness 與 Admin dependency health。
- 背景工作：`worker_service.py` 提供 durable job contract、claim/retry/DLQ 與 outbox delivery；PostgreSQL adapter 在 `repositories/worker_job_repository.py`，process 入口為 `scripts/run_worker.py`。
- 稽核：`admin_audit_service.py`

## 維護規則

- service 可以組合多個 repository。
- service 不應依賴 FastAPI request object，除非是非常明確的邊界需求。
- 失敗 fallback 要能被記錄與追蹤。
- 推薦邏輯應集中，不要散落在 route 或 frontend。
- RAG verified offer 與活動安全檢查要維持在 service 層。
