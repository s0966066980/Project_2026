# Require step-up authorization for voice evidence

Status: superseded by ADR-0064

Daily Optimization Reference Report summaries remain available through ordinary authenticated Admin access, but resolving an evidence identifier into de-identified STT text and the complete LLM answer requires the explicit `optimization.evidence.read` permission and fresh manager password reauthentication. A successful step-up remains valid for fifteen minutes and never broadens the administrator's store scope.

Every individual evidence expansion writes an audit event containing administrator identity, observation time, store, and opaque evidence identifier. The audit event never contains STT text, LLM output, or other conversation content. Expired step-up state requires reauthentication before another expansion.
