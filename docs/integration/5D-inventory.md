# Milestone 5D Inventory — Multimodal Evidence Production Cutover

## Callers

| Caller | Before | After |
| --- | --- | --- |
| `emotion_service.analyze_event` | direct `httpx` → `{provider}/predict` | `multimodal_evidence_gateway.collect_evidence` |
| Emotion-LLaMA / R1-Omni HTTP | embedded in application service | Adapter-only (`EmotionLlamaAdapter`, `R1OmniAdapter`) |

## Production path

Route → Emotion Application Service → Multimodal Gateway → Typed Evidence → Emotion log repository → optional barrier (flagged) → Intervention

Evidence is never allowed to place orders, capture payment, or issue irreversible commands (`decision_boundary=evidence_only`).

## Provider contract

- Endpoint: `{EMOTION_LLAMA_GRADIO_URL|R1_OMNI_GRADIO_URL}/predict`
- Body: `video_path`, `question`, `skip_quality_check`
- Response: `{ "result": <str|dict> }`

## Failure mode

Provider timeout / invalid / low quality → `status=no_evidence|error|skipped`; Kiosk continues; Checkout unaffected.

## Known gaps

- Full PostgreSQL evidence persistence expands with later governance; JSON emotion log remains compatibility path for default scope.
- Temp media cleanup remains route/upload owned.
