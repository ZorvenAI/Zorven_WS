"""SKL-NTA-05: RAG retrieval for prior naming documents."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retrieve prior naming documents from RAG store."""

    async def retrieve(self, tenant_id: str, query: str) -> dict[str, Any]:
        """Retrieve relevant naming documents.

        Currently returns empty — RAG integration deferred to v2.
        """
        logger.debug(
            "RAG retrieval for tenant %s: %s (not yet implemented)",
            tenant_id,
            query[:80],
        )
        return {"documents": [], "retrieval_score": 0.0}
