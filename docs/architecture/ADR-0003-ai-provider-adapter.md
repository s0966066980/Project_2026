# ADR-0003：AI Provider 使用 Port / Adapter

- 狀態：Accepted
- 日期：2026-07-13

## Context

目前 Ollama、Gemini、STT、TTS、RAG embedding、Emotion-LLaMA 與 R1-Omni 的連線、retry、模型選擇與 response parsing 分散在 service/module。Domain workflow 因此知道 provider 名稱與技術細節，API process 也可能載入大型模型。

## Decision

逐步定義能力導向 Port：

- `LLMCompletionPort`
- `SpeechToTextPort`
- `TextToSpeechPort`
- `EmbeddingSearchPort`
- `EmotionAnalysisPort`

Adapter 負責 provider SDK/HTTP、timeout、retry、circuit breaker、telemetry 與 provider-specific response。Application service 只依賴 Port 與 domain result。

Milestone 0 只記錄決策，不修改現有 provider。Milestone 1 先建立 compatibility adapter，Milestone 4 再將高成本執行移到 gateway/worker。

## Consequences

- 可在測試中使用 deterministic fake，不需要模型/GPU/network。
- 可以切換 provider、隔離 failure 與追蹤成本/latency。
- 需要定義 provider-neutral error taxonomy 與 streaming contract。

## Security and Data Rules

- Prompt 與模型 output 視為不可信資料。
- Adapter 不得記錄 Secret、完整 PII、原始音訊或未遮罩 prompt。
- 外部 provider 必須有資料處理政策、timeout、最大 payload 與 tenant policy。
- Domain action 不得直接由未驗證模型 output 執行。
