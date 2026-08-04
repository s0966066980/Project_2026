# Fix Kiosk voice interactions to Traditional Chinese

Accepted. The Kiosk UI, speech recognition, assistant responses, and TTS are deliberately fixed to Traditional Chinese, with language switching, response-language detection, and English prompt/voice settings removed. This reduces an unsupported cross-language state chain and keeps the voice contract deterministic; changing it later would require a deliberate new language policy and migration of the client/server contract.
