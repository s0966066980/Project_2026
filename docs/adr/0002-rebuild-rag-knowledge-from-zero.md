# Rebuild RAG knowledge from zero

Status: accepted

The existing RAG knowledge, retrieval index, document versions, and audit history will be permanently deleted before the redesigned knowledge system is introduced. We deliberately chose a clean reset instead of migrating the current governed documents because the new classification, retrieval methods, evaluation model, and Admin workflow should not inherit assumptions or inconsistencies from the superseded design.

The reset applies only to the superseded system. New knowledge starts a fresh Draft → Indexing → Published lifecycle, creates immutable versions when published content changes, and accumulates new audit history. Normal removal retires knowledge; it does not perform another permanent reset.

After the reset, Retired Knowledge Versions, test-case revisions, Evaluation Runs, Retrieval Configuration versions, and audit history have no automatic deletion policy. Only rebuildable index artifacts and temporary files use bounded retention.

Revising Published knowledge uses an atomic publication swap. The previous Published version remains available to retrieval while its replacement is Draft, Indexing, or Index Failed, and is retired only after the replacement is indexed successfully. This deliberately favors continuous knowledge availability over immediately reflecting an unfinished correction.

## Consequences

- The reset is irreversible and every store starts with an empty knowledge base.
- Existing RAG answers remain unavailable after the one-time reset until new knowledge is created, indexed, and evaluated.
- The cutover must prevent old workers or compatibility paths from recreating deleted knowledge.
- The redesigned API exposes only new knowledge, retrieval-configuration, test-case, evaluation-run, and retrieval-health resources; no compatibility shim preserves legacy RAG endpoints.
- The reset deletes governed knowledge and versions, object content, materialized files, keyword/vector indexes and selection state, legacy reviews/FAQ/knowledge gaps, test and evaluation data, Retrieval Configurations, alerts, and RAG job state.
- A system audit receipt preserves only the reset deployment, actor, timestamp, and deletion counts; it preserves none of the deleted RAG content.
