# Reference voice evidence without copying it into optimization reports

Status: accepted

A Daily Optimization Reference Report is retained for thirty days and stores classifications, occurrence counts, evidence levels, reference guidance, offline test results, risks, and opaque Voice Interaction Evidence identifiers. It does not copy STT text, LLM answers, or individual interaction content into the report.

An authorized Admin expansion resolves an identifier to the still-live store-scoped evidence and records an access-audit event. When Voice Interaction Evidence reaches its thirty-day expiry, the associated report reference becomes unavailable rather than retaining a second copy. The report and all remaining references are permanently deleted at the report's own thirty-day expiry.
