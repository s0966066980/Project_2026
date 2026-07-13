# TDD — Milestone 5C AI Gateway Production Cutover

## RED

1. Production services must not import `ai_services` directly.
2. Timeout must return within budget without waiting for stuck provider thread.
3. AI push structured schema requires `recommendation_id` + `push_text`.
4. AI push caller must invoke gateway task `ai_push_copy`.

## GREEN

- `tests/test_llm_gateway_production_cutover.py`
- Caller cutovers in `ai_push_service`, `voice_service`, `emotion_service`
- Long-lived `_GATEWAY_EXECUTOR` timeout path

## Classification

PRODUCTION_PATH_PASS for text LLM production callers.
