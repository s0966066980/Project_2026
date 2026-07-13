# TDD — Milestone 6A RAG Governance PostgreSQL

## RED

1. Migration 0010 must define documents/versions/publications/traces/rebuild runs.
2. Draft content_ref must point at object storage when available.
3. Rebuild must produce index_version side effect.
4. JSON import must be idempotent and count-only.

## GREEN

- `tests/test_rag_governance_durable.py`
- `repositories/rag_governance_repository.py`
- service dual path + import script

## Classification

PRODUCTION_PATH_PASS for internal durable path when postgres configured; JSON remains compatibility.
