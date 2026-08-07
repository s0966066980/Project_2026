# Retain de-identified voice interactions for thirty days

Status: accepted

Voice Turn conversation memory remains short-lived session state. A separate store-scoped Voice Interaction Evidence record may retain one individual interaction for thirty days solely for Daily Optimization Simulation and authorized manual review. It stores observation time, STT text after irreversible personal-data masking, the complete LLM answer, RAG-hit outcome, voice outcome or safe failure type, and retry or correction outcome, plus only opaque record identity and store scope required for isolation, audited access, and deletion.

Raw audio, member or device identity, session identifiers, order or payment details, and individual emotion observations are never included. Redaction runs before persistence and an event that cannot be safely de-identified is discarded instead of saving raw personal data. Records are encrypted at rest, access is authorized and audited, and the data is never used for model training. At thirty days the record and its derived indexes or backups are permanently deleted.
