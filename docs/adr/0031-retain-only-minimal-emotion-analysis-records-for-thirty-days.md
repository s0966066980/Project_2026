# Retain only minimal emotion analysis records for thirty days

Status: accepted

Periodic Ordering, Voice Only, and Live Admin Emotion Test observations share one store-scoped Emotion Analysis Record. Each record retains only time, event, model, emotion, intensity, facial evidence, vocal evidence, and overall description, plus the opaque identity and store scope required to isolate and delete it. The Admin history exposes the same analysis fields rather than a separate diagnostic or effectiveness-evidence schema.

Structured records expire after thirty days and are then permanently deleted. Raw image, video, audio, and transcript content are discarded after inference and are never part of the record. This policy provides short-lived customer-service reference without creating a reusable customer-media archive.
