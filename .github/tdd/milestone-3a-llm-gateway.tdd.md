# Milestone 3A — LLM Gateway TDD Evidence

## Source

`CODEX_AUTONOMOUS_ROADMAP.txt` Milestone 3A.

## RED

`pytest -q tests/test_llm_gateway.py` fails until `models.llm` and `services.llm_gateway_service` exist.

## GREEN

Gateway provides typed request/response, model policy chain, retry for safe errors only, fallback, schema validation metrics, timeout boundary, redacted errors, and prompt version echo. Existing `ai_services` Ollama/Gemini functions remain compatibility adapters.
