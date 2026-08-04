# Evaluate retrieval with curated store test cases

Status: accepted

Retrieval quality is measured only from store-scoped Retrieval Test Cases with administrator-curated Expected Knowledge; ad hoc and production queries never receive a fabricated hit-rate label. Every Evaluation Run snapshots the same cases and index, disables production fallback, and compares BM25, Dense Vector, Hybrid RRF, and Hybrid with Reranker under a fixed depth-ten Balanced benchmark using Hit Rate@1/@3/@5, Mean Reciprocal Rank@5, and latency. A method recommendation requires at least twenty valid cases across three categories with no category above half of the dataset, ranks Hit Rate@3 before MRR@5 and P95 latency, remains advisory, and never changes production automatically.
