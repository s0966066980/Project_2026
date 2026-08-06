# Require provider-specific authorization for customer evidence

Status: accepted

Every Daily Review Analyzer Profile defaults to the `synthetic_only` Analyzer Data Scope. Codex, Claude, and Grok are enabled independently, and enabling an analyzer does not authorize it to receive customer evidence. The `customer_evidence` scope is granted separately per provider only after an administrator supplies automation-only credentials, reviews the disclosed outbound data categories, and confirms that the provider-retention configuration satisfies deployment policy.

Each customer-evidence run records an egress audit with analyzer and version, model, effort, store, evidence identifiers and counts, and observation time without copying STT or LLM content. Missing or invalid authorization blocks the run before evidence leaves the system. No failure or model selection can upgrade data scope or redirect evidence to another provider automatically.
