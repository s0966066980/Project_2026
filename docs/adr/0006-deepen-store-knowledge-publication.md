# Deepen Store Knowledge Base publication

Status: accepted

Store Knowledge Base publication will live in one deep module that owns the Knowledge Version lifecycle, per-item Publication Attempt, Publication Batch outcomes, phase-aware resume, atomic publication swap, audit, and cleanup. Durable publication state is the only source of truth for Published knowledge; versioned index artifacts are derived, remain invisible until the swap commits, and cannot make themselves Published merely by existing.

Each Knowledge Item may have at most one publication attempt in flight while newer Draft versions continue to be authored. Index build failures become Index Failed, successful builds whose swap cannot commit become Publication Failed, and cleanup failure after a successful swap never rolls back the new Published version; the job adapter owns delivery and backoff but never domain transitions.

The publication module will replace the monolithic Store Knowledge Base state blob with independent store-scoped durable records for Knowledge Items, Knowledge Versions, Publication Attempts, the Published version pointer, and audit events. Postgres is the production adapter, SQLite is the Local Development Runtime and test adapter, Publication Attempt metadata is retained as audit history, and staged or failed artifacts default to thirty-day retention while active attempts are exempt.

## Consequences

- The cutover follows ADR-0002: no compatibility shim or dual-write preserves the superseded state blob.
- Interface tests use SQLite plus scripted job and index adapters, replacing tests coupled to helper functions or positional calls.
- Retrieval Configuration, Retrieval Test Case, Evaluation Run, and Online Retrieval Health remain outside this module because their rules and interfaces are independent.
