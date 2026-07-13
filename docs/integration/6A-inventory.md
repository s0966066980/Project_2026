# Milestone 6A Inventory — RAG Governance PostgreSQL Persistence

## Persistence

| Layer | Location |
| --- | --- |
| Metadata SoT (production) | PostgreSQL `rag_documents`, `rag_document_versions`, `rag_publications`, `rag_retrieval_traces`, `rag_rebuild_runs` (migration 0010) |
| Content binary | Object storage (`content_ref=object:...`) |
| Compatibility | JSON `learning_data/rag_asset_versions.json` when `MEMBER_STORAGE_BACKEND!=postgres` |

## Production path

create_draft → object storage content_ref → version row  
submit_for_review / publish → state machine + publication pointer  
rebuild worker handler → index_version side effect + rebuild_run  
retrieval → published-only candidates + optional durable trace  

## Import

`python backend/scripts/import_rag_governance_json.py` — idempotent, count-only.

## Known gaps

- Full embedding index write still uses existing Chroma path; 6A durable-izes governance metadata and rebuild side effects.
- Multi-instance publish concurrency relies on DB unique constraints when postgres is active.
