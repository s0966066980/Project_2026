"""RAG asset lifecycle and retrieval-trace contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID


class RagAssetStatus(str, Enum):
    DRAFT = "draft"
    INDEXING = "indexing"
    INDEX_FAILED = "index_failed"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    RETIRED = "retired"
    FAILED = "failed"


RAG_PERMISSIONS = frozenset(
    {
        "rag.read",
        "rag.write",
        "rag.publish",
    }
)


@dataclass
class RagAssetVersion:
    document_id: str
    version: int
    status: RagAssetStatus
    source: str
    checksum: str
    owner: str
    tenant_id: UUID | None = None
    store_id: UUID | None = None
    created_at: str = ""
    reviewed_at: str = ""
    published_at: str = ""
    superseded_at: str = ""
    content_ref: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalTrace:
    query_ref: str
    document_versions: list[str]
    chunk_ids: list[str]
    scores: list[float]
    provider: str
    latency_ms: float
    schema_version: str = "retrieval-trace-v1"
