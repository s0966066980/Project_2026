# Simplify Admin RAG knowledge management

Status: superseded by ADR-0002

The Admin will use one store-scoped RAG knowledge model instead of separate structured FAQ and generic document workflows. Structured FAQ support and every knowledge version with the `faq` source type will be permanently deleted without migration; the remaining legacy types will map to Store Information, Menu Information, Promotion Information, or Other. The editor will require only Knowledge Type and Knowledge Content, while the system supplies the stable identifier and display title.

Knowledge moves from Draft to Indexing and becomes Published only after the background index update succeeds; a failed update becomes Index Failed and may be retried. Editing a Published document immediately removes the old version from retrieval, so the system deliberately provides no fallback answer while the replacement is being indexed. Normal removal uses Retired and preserves version and audit history.

The Admin surface will keep knowledge management and retrieval testing prominent, move technical controls into a collapsed advanced section, and remove manual source selection, validation, and rebuild steps. The test shows matches from the current store's formal index rather than generating an LLM answer. RAG management will use one v1 knowledge/test API, with the legacy reviews, docs, and FAQ management endpoints removed.

Only a principal with both `admin_identity.manage` and `rag.publish` may publish, retry indexing, or retire knowledge. Principals with `rag.write` may create and revise Draft versions but cannot affect the formal index.

## Consequences

- Deleting all `faq`-typed data is intentionally irreversible and may remove generic text that was previously classified as FAQ.
- A Published document being revised becomes temporarily unavailable until its replacement finishes indexing.
- The four fixed Knowledge Types improve consistency but deliberately remove free-form classification.
