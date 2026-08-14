# Withhold conversation text until step-up is approved

Status: accepted

Admin needs a searchable Voice Interaction Evidence list and Daily Operations Diagnostic Workbench needs the same de-identified records, but Device-Authenticated Admin Access currently has no independent verifier that could establish the step-up assumed by ADR-0046. The current release therefore exposes record metadata and aggregate diagnosis only: it retains masked STT and assistant text for bounded internal analysis but provides no browser or API path that reveals them. Device authentication and `optimization.evidence.read` cannot substitute for step-up. Full conversation expansion remains unavailable until a separate verifier, bounded authorization lifetime, rate limiting, and content-free access audit are explicitly approved.
