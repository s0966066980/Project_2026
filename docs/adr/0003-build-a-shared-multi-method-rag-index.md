# Build a shared multi-method RAG index

Status: accepted

Every Published knowledge version will build keyword, dense-vector, and reranking candidate artifacts as one versioned store-scoped index. BM25, Dense Vector, Hybrid RRF, and Hybrid with Reranker therefore evaluate the same Knowledge Chunks and can become the store's Published Retrieval Method without another rebuild. We accept higher indexing time and storage usage to make method comparisons reproducible and production switching immediate.

If a Published Hybrid-with-Reranker configuration cannot reach its reranking model, retrieval temporarily falls back to Hybrid RRF without modifying the Published Retrieval Configuration. Online Retrieval Health reports the degraded state and fallback count, and the original method resumes automatically when the reranker recovers.

Dense failure falls back to BM25; Hybrid RRF uses whichever keyword or dense path remains healthy; Hybrid with Reranker first falls back to Hybrid RRF and then follows the same rule. If every path fails, retrieval returns no knowledge rather than consulting another store or an obsolete index. Every fallback is observable as degraded Online Retrieval Health.

Embedding, reranker, chunking, or algorithm-preset upgrades never replace production silently. They build a new index version, run a comparable Evaluation Run, and require explicit publication of a Retrieval Configuration referencing that version.

Each store retains the current production index and the immediately previous production index. The previous index expires after thirty days unless a Published Retrieval Configuration still references it, in which case cleanup is deferred.
