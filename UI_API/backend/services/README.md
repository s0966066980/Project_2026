# Backend Services

`services/` 是過渡期 application/business layer，組合 repositories、provider ports 與 workflow；Identity 已抽至 `modules/identity`，其他 domain 仍主要位於此層。

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
