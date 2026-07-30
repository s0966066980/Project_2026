# Deepen Voice Turn orchestration

Status: accepted

Voice ordering will be split into two deep modules joined by a strict streaming protocol. The Backend Voice Turn module owns STT, Voice Menu Candidate Set selection, assistant execution, Voice Order Draft creation, TTS synthesis reporting, and the durable lifecycle `Accepted → Transcribing → Assisting → Synthesizing → Completed`, with Transcription Failed and Assistant Failed terminal states. The Kiosk Voice Turn module owns recording, cancellation, no-speech detection, transport, display, actual audio playback, draft confirmation, and the single visible terminal outcome.

Every accepted request has a stable `voice_turn_id` scoped to one store and ordering session, and produces exactly one terminal event. Backend phase outputs are durably recorded so process restart resumes from the last successful phase without rerunning completed STT, assistant, Draft, or observation work. Disconnecting a Kiosk ends only its subscription; it does not cancel accepted backend work. Completed results remain replayable for the ordering session and a short retention period, without retaining raw audio merely for idempotency.

The streaming contract uses a durable, monotonically sequenced event journal. A reconnect supplies its last acknowledged sequence and receives only later events. Repeating an identical sequence and payload is an ignorable transport duplicate; gaps, conflicting duplicates, malformed or unknown events, events after terminal, EOF before terminal, and a second distinct terminal are protocol failures. The Kiosk maps protocol failure to assistant failure while preserving already displayed validated text.

Only the Backend Voice Turn module may produce a validated Voice Order Draft. The Kiosk presents and confirms it but never converts legacy cart actions or ambiguous assistant output into cart mutations, and a new Voice Turn cannot begin while a Draft awaits confirmation. Voice Emotion Observation is scheduled as asynchronous correlated work and never delays or changes its originating Voice Turn. Only a successfully completed assistant result enters later session history; TTS synthesis or playback failure does not invalidate that text result.

## Consequences

- The buffered `/api/ask` path and the legacy `cart_actions` fallback are deleted; the resumable streaming path is the sole Voice Turn transport.
- Transient adapter failures receive bounded exponential retry with stable phase operation keys. Validation, authorization, and scope failures do not retry; exhausted STT or assistant work reaches its corresponding failure terminal, while exhausted TTS preserves the successful text and reports synthesis unavailable.
- Backend tests exercise the module interface with scripted STT, assistant, menu, TTS, and observation adapters. Kiosk tests use fake recording, clock, transport, audio, and cart adapters. Thin route tests and a small browser smoke suite remain; private-helper, source-inspection, and duplicated callback tests are removed.
