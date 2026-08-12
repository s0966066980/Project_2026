"""Published Knowledge/RAG application surface."""

from modules.knowledge_publication import KnowledgePublicationModule, PublicationError, TransientPublicationError
from modules.knowledge_publication import _knowledge_service as rag_knowledge_service
from modules.knowledge_publication import runtime as knowledge_publication_runtime
from modules.retrieval_check import RetrievalCheckError, RetrievalCheckModule, RetrievalIdentity
from modules.retrieval_check import runtime as retrieval_check_runtime
from modules.retrieval_configuration import RetrievalConfigurationError, RetrievalConfigurationModule

# The knowledge rules used to be reached by a call-time proxy into services/,
# which is what kept this capability on the frozen legacy-layer list — and the
# service imported this surface back, so the proxy was also breaking a cycle.
# Both ends are gone: the rules live in modules/knowledge_publication.

__all__ = [
    "KnowledgePublicationModule",
    "knowledge_publication_runtime",
    "PublicationError",
    "TransientPublicationError",
    "RetrievalCheckError",
    "RetrievalCheckModule",
    "RetrievalConfigurationError",
    "RetrievalConfigurationModule",
    "RetrievalIdentity",
    "retrieval_check_runtime",
    "rag_knowledge_service",
]
