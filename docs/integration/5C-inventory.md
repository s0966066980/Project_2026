# Milestone 5C Inventory — AI Gateway Production Cutover

## Current caller → Production path

| Caller | Before | After |
| --- | --- | --- |
| `ai_push_service` | `ai_services.ask_ollama` | `llm_gateway_service.generate` task=`ai_push_copy` |
| `voice_service` | `ai_services.ask_ollama` | `llm_gateway_service.generate` task=`voice_assist` |
| `emotion_service` payment assist | `ai_services.ask_ollama` | task=`payment_assist` |
| `emotion_service` emotion extract | `ai_services.ask_ollama` | task=`emotion_extract` |

## Allowed ai_services imports

| Module | Role |
| --- | --- |
| `llm_gateway_service.OllamaAdapter` | Provider adapter |
| `llm_gateway_service.GeminiAdapter` | Provider adapter |
| `test_service` | Test/debug routes only |
| `bootstrap/startup` | Gemini client warm-up (not generation) |

## Persistence / fallback

- Menu whitelist and verified offer guard remain in application service after Gateway.
- Gateway timeout uses long-lived executor; caller returns within timeout budget.
- Fallback text remains for AI push when Gateway errors/schema fails.

## Known gaps

- Multimodal Emotion-LLaMA / R1-Omni HTTP path cutover is Milestone 5D.
- RAG generative callers (if any beyond retrieval) expand with governance callers.
