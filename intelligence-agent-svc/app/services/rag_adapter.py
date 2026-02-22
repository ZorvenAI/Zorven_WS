"""
Vertex AI RAG adapter for querying historical brand context.

In stub mode (no RAG config), returns empty results.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RAGAdapter:
    """Query Vertex AI RAG for historical brand context."""

    def __init__(
        self,
        project_id: str = "",
        location: str = "us-central1",
    ) -> None:
        self.project_id = project_id
        self.location = location
        self._stub_mode = not project_id

        if self._stub_mode:
            logger.info("RAGAdapter running in stub mode (no RAG config)")
        else:
            logger.info(
                "RAGAdapter configured for project: %s, location: %s",
                project_id,
                location,
            )

    async def query(self, query: str, data_store_id: str = "") -> list[str]:
        """
        Query Vertex AI RAG for relevant historical findings.

        Args:
            query: Search query text.
            data_store_id: Vertex AI data store identifier.

        Returns:
            List of relevant text snippets from RAG.
        """
        if self._stub_mode:
            logger.debug("RAGAdapter stub: no historical data for query")
            return []

        try:
            # Vertex AI Search integration
            from google.cloud import aiplatform

            aiplatform.init(project=self.project_id, location=self.location)

            # Use Vertex AI Search to query the data store
            # This is a simplified interface — production would use
            # the full Vertex AI Search SDK
            logger.info("RAG query: '%s' (store: %s)", query[:50], data_store_id)

            # TODO: Implement full Vertex AI Search query
            # For now, return empty until RAG infrastructure is deployed
            return []

        except Exception as exc:
            logger.warning("RAG query failed: %s", exc)
            return []

    async def get_historical_valuations(
        self, tenant_id: str, brand_name: str = ""
    ) -> list[dict[str, Any]]:
        """
        Retrieve historical brand valuations for trend analysis.

        Returns:
            List of historical valuation records.
        """
        if self._stub_mode:
            return []

        try:
            query = f"brand valuation history {brand_name} tenant:{tenant_id}"
            results = await self.query(query)
            return [{"text": r} for r in results]
        except Exception as exc:
            logger.warning("Historical valuation query failed: %s", exc)
            return []
