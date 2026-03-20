import logging

from decouple import config

logger = logging.getLogger(__name__)


class RAGSearchClient:
    """Lightweight search client for Vertex AI Discovery Engine.

    Used by BrandAffinityVerifier Tier 3 to cross-reference brand identity
    documents stored in the tenant's RAG data store.
    """

    def __init__(self):
        self._client = None
        self._project = config("GCP_PROJECT_ID", default="")
        self._location = config("GCP_LOCATION", default="global")

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google.cloud import discoveryengine_v1

            self._client = discoveryengine_v1.SearchServiceClient()
            return self._client
        except ImportError:
            logger.debug("discoveryengine SDK not available")
            return None
        except Exception as e:
            logger.warning("Failed to initialize SearchServiceClient: %s", e)
            return None

    def query(self, data_store_id: str, query_text: str, top_k: int = 3) -> list[dict]:
        """Query a Vertex AI data store for relevant documents.

        Args:
            data_store_id: The data store ID to search.
            query_text: The search query text.
            top_k: Maximum number of results to return.

        Returns:
            List of dicts with 'content' and 'score' keys.
        """
        client = self._get_client()
        if not client or not self._project or not data_store_id:
            return []

        try:
            from google.cloud import discoveryengine_v1

            serving_config = (
                f"projects/{self._project}/locations/{self._location}"
                f"/dataStores/{data_store_id}/servingConfigs/default_config"
            )

            request = discoveryengine_v1.SearchRequest(
                serving_config=serving_config,
                query=query_text,
                page_size=top_k,
            )

            response = client.search(request=request, timeout=5.0)

            results = []
            for result in response.results:
                doc_data = {}
                if hasattr(result, "document") and result.document:
                    doc = result.document
                    if hasattr(doc, "derived_struct_data"):
                        snippets = doc.derived_struct_data.get("snippets", [])
                        if snippets:
                            doc_data["content"] = snippets[0].get("snippet", "")
                    if not doc_data.get("content") and hasattr(doc, "content"):
                        content = doc.content
                        if hasattr(content, "raw_bytes"):
                            doc_data["content"] = content.raw_bytes.decode(
                                "utf-8", errors="ignore"
                            )[:500]
                doc_data["score"] = getattr(result, "relevance_score", 0.0)
                if doc_data.get("content"):
                    results.append(doc_data)

            return results

        except Exception as e:
            logger.warning("RAG query failed for data_store %s: %s", data_store_id, e)
            return []
