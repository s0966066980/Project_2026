# Pin browser voice activity detection to Silero VAD v5

Status: accepted

Menu-Wide Voice Listening uses the Silero VAD v5 ONNX model through project-bundled, version-pinned browser assets. The model, ONNX Runtime Web files, and audio worklet are served by the application rather than a CDN or `latest` dependency, even though newer Silero releases exist, because the established browser wrapper directly supports v5 and one fixed artifact keeps offline operation, kiosk startup, speech-boundary tuning, and acceptance evidence reproducible. Moving to another model version requires an explicit replacement decision and fresh noisy-store browser acceptance rather than an automatic dependency upgrade.
