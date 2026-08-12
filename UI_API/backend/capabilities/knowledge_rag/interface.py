"""Published Knowledge/RAG application surface."""

from modules.knowledge_publication import KnowledgePublicationModule, PublicationError, TransientPublicationError
from modules.knowledge_publication import runtime as knowledge_publication_runtime
from modules.retrieval_check import RetrievalCheckError, RetrievalCheckModule, RetrievalIdentity
from modules.retrieval_check import runtime as retrieval_check_runtime
from modules.retrieval_configuration import RetrievalConfigurationError, RetrievalConfigurationModule


class _RagKnowledgeServiceProxy:
    """Resolve the service at call time.

    `services.rag_knowledge_service` imports this capability, so importing it
    back here at module scope is a circular import. Consumers that need to name
    its error classes in an annotation import them under `TYPE_CHECKING`.
    """

    def __getattr__(self, name: str):
        from services import rag_knowledge_service

        return getattr(rag_knowledge_service, name)


rag_knowledge_service = _RagKnowledgeServiceProxy()

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
