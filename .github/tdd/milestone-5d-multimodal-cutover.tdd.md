# TDD — Milestone 5D Multimodal Evidence Production Cutover

## RED

1. `emotion_service` must not import `httpx` or hardcode `/predict`.
2. Only gateway adapters may call provider HTTP.
3. `analyze_event` must call gateway and tolerate no-evidence without raising.
4. Successful gateway signals map into log entry; boundary remains evidence-only.

## GREEN

- `tests/test_multimodal_evidence_production_cutover.py`
- Adapter `/predict` alignment in `multimodal_evidence_gateway.py`
- `emotion_service.analyze_event` cutover

## Classification

PRODUCTION_PATH_PASS for main Emotion route.
