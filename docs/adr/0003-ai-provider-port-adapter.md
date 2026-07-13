# ADR-0003：AI Provider 使用 Port / Adapter

- 狀態：Accepted
- 日期：2026-07-13
- Owner：AI Platform

## Context

系統同時使用 Ollama、Gemini、STT、TTS、RAG embedding、Emotion-LLaMA 與 R1-Omni。若 application workflow 直接知道 provider 名稱、SDK、URL 與 response 細節，會提高耦合，也讓模型切換、測試、timeout、fallback 與商用部署變困難。

## Decision

逐步定義能力導向 Port：

```text
TextGenerationPort
SpeechToTextPort
TextToSpeechPort
EmbeddingPort
EmotionAnalysisPort
```

Provider 實作放在 Adapter/Gateway：

```text
OllamaAdapter
GeminiAdapter
WhisperAdapter
EdgeTtsAdapter
EmotionLlamaAdapter
R1OmniAdapter
```

Application service 只依賴標準 request/response，不依賴 provider SDK 或原始 payload。

Gateway/Adapter 負責：

- timeout、retry、circuit breaker 與 fallback；
- provider authentication；
- response normalization 與 schema validation；
- latency、error、token/cost 與 model version metrics；
- 隱私遮罩與必要 audit metadata。

大型模型不得成為核心 API process 的必要 import 或啟動條件。

## Consequences

正面：

- 可替換本地與雲端模型。
- 測試可使用 fake adapter，不需要 GPU 或外部 API。
- Provider 故障與高延遲較容易隔離。
- 商用授權、成本與版本可獨立治理。

代價：

- 需要維護標準 contract 與 provider capability matrix。
- 不同模型能力差異可能需要 feature negotiation。
- 遷移期間會存在舊 service 呼叫與新 adapter 的相容層。

## Alternatives

- Domain 直接呼叫各 Provider SDK：實作較快，但長期耦合與測試成本高。
- 將全部 AI 功能立即拆成獨立 Microservices：目前不必要，先建立 Port/Adapter 與 Gateway boundary。
