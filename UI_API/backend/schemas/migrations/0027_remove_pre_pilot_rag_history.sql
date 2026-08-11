-- Batch P1: remove the pre-pilot RAG aggregate and its superseded governance
-- tables. Knowledge publication state and ad hoc retrieval checks are owned by
-- later migrations and deliberately remain.
--
-- This is a one-way cutover. The receipt stores row counts only; it never copies
-- knowledge content, queries, embeddings, or the old aggregate JSON.

CREATE TABLE IF NOT EXISTS retrieval_configurations (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    version BIGINT NOT NULL CHECK (version > 0),
    method TEXT NOT NULL CHECK (method IN ('bm25', 'dense', 'hybrid_rrf', 'hybrid_reranker')),
    top_k INTEGER NOT NULL CHECK (top_k IN (3, 5, 10)),
    relevance_policy TEXT NOT NULL CHECK (relevance_policy IN ('lenient', 'balanced', 'strict')),
    preset_version TEXT NOT NULL,
    index_version TEXT NOT NULL,
    published_at TEXT NOT NULL,
    published_by TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores (tenant_id, id)
);

-- Preserve only the one active configuration. Historical configurations and all
-- other fields in the Studio aggregate are intentionally not migrated.
INSERT INTO retrieval_configurations (
    tenant_id, store_id, version, method, top_k, relevance_policy,
    preset_version, index_version, published_at, published_by
)
SELECT DISTINCT ON (s.tenant_id, s.store_id)
    s.tenant_id,
    s.store_id,
    (configuration->>'version')::BIGINT,
    configuration->>'method',
    (configuration->>'top_k')::INTEGER,
    configuration->>'relevance_policy',
    COALESCE(configuration->>'preset_version', 'rag-preset-2026.1'),
    COALESCE(configuration->>'index_version', 'shared-multi-method-2026.1'),
    COALESCE(configuration->>'published_at', NOW()::TEXT),
    COALESCE(configuration->>'published_by', 'migration:0027')
FROM rag_studio_states AS s
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(s.state->'configurations', '[]'::jsonb)) AS configuration
WHERE configuration->>'status' = 'published'
  AND (configuration->>'version') ~ '^[0-9]+$'
  AND (configuration->>'version')::BIGINT > 0
  AND (configuration->>'top_k')::INTEGER IN (3, 5, 10)
  AND configuration->>'method' IN ('bm25', 'dense', 'hybrid_rrf', 'hybrid_reranker')
  AND configuration->>'relevance_policy' IN ('lenient', 'balanced', 'strict')
ORDER BY s.tenant_id, s.store_id, (configuration->>'version')::BIGINT DESC
ON CONFLICT (tenant_id, store_id) DO NOTHING;

DO $$
DECLARE
    removed_counts JSONB := '{}'::JSONB;
    table_name TEXT;
    row_count BIGINT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'rag_documents',
        'rag_document_versions',
        'rag_publications',
        'rag_retrieval_traces',
        'rag_rebuild_runs',
        'rag_studio_states',
        'rag_asset_scopes'
    ] LOOP
        IF to_regclass('public.' || table_name) IS NOT NULL THEN
            EXECUTE format('SELECT COUNT(*) FROM public.%I', table_name) INTO row_count;
            removed_counts := removed_counts || jsonb_build_object(table_name, row_count);
        ELSE
            removed_counts := removed_counts || jsonb_build_object(table_name, 0);
        END IF;
    END LOOP;

    INSERT INTO rag_reset_receipts (
        id, deployment_id, actor, deletion_counts, contains_content
    ) VALUES (
        gen_random_uuid(),
        current_setting('application_name', TRUE),
        'migration:0027',
        removed_counts,
        FALSE
    );
END $$;

DROP TABLE IF EXISTS rag_retrieval_traces;
DROP TABLE IF EXISTS rag_rebuild_runs;
DROP TABLE IF EXISTS rag_publications;
DROP TABLE IF EXISTS rag_document_versions;
DROP TABLE IF EXISTS rag_documents;
DROP TABLE IF EXISTS rag_studio_states;
DROP TABLE IF EXISTS rag_asset_scopes;
