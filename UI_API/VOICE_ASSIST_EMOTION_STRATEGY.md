# Voice Assist and Emotion-LLaMA Strategy

## Scope

Emotion-LLaMA is not a continuous monitor. It is used only when the patent flow has already produced an event-triggered short clip or when an administrator explicitly starts the independent client for testing.

## Runtime Policy

- `Emotion-LLaMA/app_EmotionLlamaClient.py` remains an independent process.
- `UI_API/main.py` does not preload Emotion-LLaMA.
- Admin can start it through `/api/emotion_llama/start` and stop it through `/api/emotion_llama/stop`.
- `VOICE_ASSIST_EMOTION_AUTO_START` defaults to `false`; voice assist should reuse the latest `emotion_cache` produced by triggered multimodal analysis.
- `VOICE_ASSIST_EMOTION_IDLE_TIMEOUT_SEC` defines the intended idle release window for a future scheduler; the current safe path is explicit stop from admin tooling.

## Data Flow

1. POS interaction events calculate `risk_score`.
2. High risk triggers the short media clip path.
3. The multimodal route runs Whisper and Emotion-LLaMA when available.
4. Structured emotion is cached per `session_id`.
5. Voice assist reads the latest cached emotion as optional context and does not start periodic emotion analysis.

This keeps the system aligned with the PPT claim: event-triggered multimodal evidence, then barrier inference and intervention, rather than always-on surveillance.
