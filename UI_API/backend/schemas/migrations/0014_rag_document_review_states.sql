-- Add explicit review outcomes to the governed RAG document lifecycle.
-- Forward-only: older application versions remain compatible with existing rows,
-- but must not write new approved/rejected rows after this migration is rolled forward.

ALTER TABLE rag_document_versions
    DROP CONSTRAINT rag_document_versions_status_check;

ALTER TABLE rag_document_versions
    ADD CONSTRAINT rag_document_versions_status_check
    CHECK (status IN ('draft', 'review', 'approved', 'rejected', 'published', 'retired', 'failed'));
