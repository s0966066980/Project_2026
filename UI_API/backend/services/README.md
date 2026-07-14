# Backend Services

`services/` 是過渡期 application/business layer，組合 repositories、provider ports 與 workflow。新 domain 應優先抽到 `modules/<domain>/application.py`，但不能建立空殼模組。

> 實作盤點：2026-07-14。

## 主要服務群

- Identity/scope：Admin access/authorization/identity compatibility shims、Device identity、commercial context/readiness/scope。
- Member/privacy：member lifecycle、preferences、versioned PII key provider、phone encryption/masking。
- Commerce：availability、promotion/banner、checkout pricing、checkout workflow、payment gateway。
- Recommendation：context、engine、events、feedback、experiments、governance、AI push。
- RAG：provider、documents、review lifecycle、governance、offer guard、alerts、object storage。
- Voice/multimodal：voice、STT、TTS、passive voice、LLM gateway、Emotion/R1 evidence gateway。
- Intervention：interaction events、barrier inference、scenario/action decision、intervention pipeline/stats。
- Operations：health、observability/audit、fleet management、analytics pipeline、shared infrastructure。
- Async：worker service/store contracts、handler registry、production handlers、outbox delivery router。

## 重要現況

- `admin_identity_service.py`、`admin_access_service.py`、`admin_authorization_service.py` 只做 `modules/identity` 相容 re-export，不新增功能。
- `payment_gateway_service.py` 與 POS integration 目前連到 manual adapters；pending manual result 不是成功扣款或已送單。
- `llm_gateway_service.py` 提供 Ollama/Gemini typed contract、timeout/retry/fallback；multimodal gateway 對 Emotion-LLaMA/R1-Omni 也必須降級安全。
- `worker_service.py` 支援 idempotency、claim、visibility timeout、retry、DLQ 與 outbox ACK；process 入口是 `scripts/run_worker.py`。
- `object_storage_service.py` 支援 memory(test)、local 與 S3 contract、signed access、encryption；metadata 可持久化至 PostgreSQL。

## 維護規則

- Service 負責 use case、交易順序與業務規則，不處理 FastAPI Request/Response 或 HTML rendering。
- 跨 domain 只呼叫公開 Application API/typed contract/event，不 import 對方 internal repository/adapter。
- Blocking DB/HTTP/model calls 不直接阻塞 async event loop。
- Checkout、價格、promotion eligibility、order transition 與 permission 以 server policy 為準。
- Provider fallback 必須可觀察且不得偽造成功；AI/RAG/voice/emotion failure 不阻擋 checkout。
- Service 變更至少跑最近的 unit/use-case test；涉及 auth、scope、checkout 或 PII 再跑對應 security/integration tests。
