-- Add the simplified knowledge indexing lifecycle while preserving legacy
-- review states long enough for historical records to remain readable.
ALTER TABLE rag_document_versions
    DROP CONSTRAINT IF EXISTS rag_document_versions_status_check;

ALTER TABLE rag_document_versions
    ADD CONSTRAINT rag_document_versions_status_check
    CHECK (
        status IN (
            'draft',
            'indexing',
            'index_failed',
            'review',
            'approved',
            'rejected',
            'published',
            'retired',
            'failed'
        )
    );
