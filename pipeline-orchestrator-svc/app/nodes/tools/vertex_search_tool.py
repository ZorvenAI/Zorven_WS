"""Vertex AI Search tool for querying tenant document data stores."""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from typing import Optional

from google.api_core.exceptions import NotFound, PermissionDenied
from google.cloud import discoveryengine_v1 as discoveryengine

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


@dataclass
class SearchChunk:
    """A single search result chunk from Vertex AI Search."""

    text: str
    source_uri: str
    source_name: str
    relevance_score: float


class VertexSearchTool:
    """Queries Vertex AI Discovery Engine for tenant-scoped document chunks.

    When a per-tenant data store ID is provided (resolved by Django via
    ``Tenant.get_data_store_id()``), it is used directly.  Otherwise
    falls back to the shared default configured via
    ``VERTEX_AI_DATA_STORE_ID``.
    """

    def __init__(self) -> None:
        self._client: Optional[discoveryengine.SearchServiceClient] = None

    def _get_client(self) -> discoveryengine.SearchServiceClient:
        """Lazy-init the Discovery Engine search client."""
        if self._client is None:
            if settings.GCS_CREDENTIALS_JSON:
                try:
                    import json as _json

                    from google.oauth2 import service_account as _sa

                    info = _json.loads(settings.GCS_CREDENTIALS_JSON)
                    creds = _sa.Credentials.from_service_account_info(info)
                    self._client = discoveryengine.SearchServiceClient(
                        credentials=creds
                    )
                except Exception:
                    logger.warning(
                        "Failed to parse GCS_CREDENTIALS_JSON for Vertex AI, "
                        "falling back to ADC"
                    )
                    self._client = discoveryengine.SearchServiceClient()
            else:
                self._client = discoveryengine.SearchServiceClient()
        return self._client

    def _get_data_store_path(
        self, tenant_id: str, data_store_id: Optional[str] = None
    ) -> str:
        """Build the fully qualified data store path for a tenant.

        When ``data_store_id`` is provided (resolved by Django's
        ``Tenant.get_data_store_id()``), it is the final data store
        name and is used directly.  Otherwise falls back to the
        shared default from settings.
        """
        store_id = data_store_id or settings.VERTEX_AI_DATA_STORE_ID
        return (
            f"projects/{settings.VERTEX_AI_PROJECT_ID}"
            f"/locations/{settings.VERTEX_AI_LOCATION}"
            f"/collections/default_collection/dataStores/{store_id}"
        )

    def _get_base_data_store_path(self, data_store_id: Optional[str] = None) -> str:
        """Build the data store path using the shared default store."""
        return (
            f"projects/{settings.VERTEX_AI_PROJECT_ID}"
            f"/locations/{settings.VERTEX_AI_LOCATION}"
            f"/collections/default_collection/dataStores/"
            f"{settings.VERTEX_AI_DATA_STORE_ID}"
        )

    @staticmethod
    def _get_cache_key(tenant_id: str, query: str) -> str:
        """Build a Redis cache key for the query."""
        query_hash = hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]
        return f"rag:query:cache:{tenant_id}:{query_hash}"

    async def search(
        self,
        query: str,
        tenant_id: str,
        data_store_id: Optional[str] = None,
        max_results: int = 5,
    ) -> list[SearchChunk]:
        """Search for relevant document chunks in the tenant's data store.

        Args:
            query: The search query string.
            tenant_id: Tenant identifier for data store scoping.
            data_store_id: Optional override for the data store ID.
            max_results: Maximum number of results to return.

        Returns:
            List of SearchChunk results. Empty list on error.
        """
        if not query or not query.strip():
            return []

        # Check Redis cache first
        cache_key = self._get_cache_key(tenant_id, query)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Cache hit for query: %s (tenant=%s)", query[:50], tenant_id)
            return cached

        # Query Vertex AI Search
        chunks = await self._query_vertex(query, tenant_id, data_store_id, max_results)

        # Cache results (non-fatal if Redis is unavailable)
        await self._set_cached(cache_key, chunks)

        return chunks

    async def _get_cached(self, cache_key: str) -> Optional[list[SearchChunk]]:
        """Retrieve cached search results from Redis."""
        try:
            redis = await get_redis()
            raw = await redis.get(cache_key)
            if raw:
                data = json.loads(raw)
                return [SearchChunk(**item) for item in data]
        except Exception:
            logger.warning("Redis cache read failed for %s", cache_key, exc_info=True)
        return None

    async def _set_cached(self, cache_key: str, chunks: list[SearchChunk]) -> None:
        """Store search results in Redis cache."""
        try:
            redis = await get_redis()
            data = json.dumps([asdict(c) for c in chunks])
            await redis.set(cache_key, data, ex=settings.RAG_QUERY_CACHE_TTL)
        except Exception:
            logger.warning("Redis cache write failed for %s", cache_key, exc_info=True)

    async def _query_vertex(
        self,
        query: str,
        tenant_id: str,
        data_store_id: Optional[str],
        max_results: int,
    ) -> list[SearchChunk]:
        """Execute a search request against the Vertex AI Discovery Engine.

        Tries the resolved data store first (per-tenant or override).
        If not found, falls back to the shared base data store.
        """
        primary = self._get_data_store_path(tenant_id, data_store_id)
        fallback = self._get_base_data_store_path()

        paths_to_try = [primary]
        if fallback != primary:
            paths_to_try.append(fallback)

        for data_store_path in paths_to_try:
            chunks = self._search_data_store(
                data_store_path, query, tenant_id, max_results
            )
            if chunks is not None:
                return chunks

        return []

    def _search_data_store(
        self,
        data_store_path: str,
        query: str,
        tenant_id: str,
        max_results: int,
    ) -> Optional[list[SearchChunk]]:
        """Search a single data store. Returns None if store not found."""
        serving_config = f"{data_store_path}/servingConfigs/default_search"

        try:
            client = self._get_client()
            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=max_results,
            )
            response = client.search(request=request)

            chunks: list[SearchChunk] = []
            for result in response.results:
                doc = result.document
                text = ""
                source_uri = ""
                source_name = ""

                # Try derived_struct_data first (unstructured stores)
                if doc.derived_struct_data:
                    snippets = doc.derived_struct_data.get("snippets", [])
                    if snippets:
                        text = snippets[0].get("snippet", "")
                    extractive = doc.derived_struct_data.get("extractive_answers", [])
                    if extractive and not text:
                        text = extractive[0].get("content", "")
                    link = doc.derived_struct_data.get("link", "")
                    source_uri = link if link else ""
                    title = doc.derived_struct_data.get("title", "")
                    source_name = title if title else ""

                # Fall back to struct_data (structured/NO_CONTENT stores)
                if doc.struct_data:
                    if not text:
                        text = doc.struct_data.get("extracted_text", "")
                    if not source_uri:
                        source_uri = doc.struct_data.get("source_gcs_uri", "")
                    if not source_name:
                        # Extract filename from GCS URI
                        gcs_uri = doc.struct_data.get("source_gcs_uri", "")
                        if gcs_uri:
                            source_name = gcs_uri.rsplit("/", 1)[-1]
                            # Remove UUID prefix (e.g., "84c891b3_")
                            if "_" in source_name:
                                source_name = source_name.split("_", 1)[1]

                if not source_name and doc.name:
                    source_name = doc.name.split("/")[-1]

                if text:
                    chunks.append(
                        SearchChunk(
                            text=text,
                            source_uri=source_uri,
                            source_name=source_name,
                            relevance_score=getattr(result, "relevance_score", 0.0),
                        )
                    )

            logger.info(
                "Vertex AI Search returned %d chunks for tenant=%s "
                "store=%s query=%s",
                len(chunks),
                tenant_id,
                data_store_path.split("/")[-1],
                query[:50],
            )
            return chunks

        except NotFound:
            logger.info(
                "Data store not found, trying next: tenant=%s path=%s",
                tenant_id,
                data_store_path,
            )
            return None
        except PermissionDenied:
            logger.error(
                "Permission denied for data store tenant=%s path=%s",
                tenant_id,
                data_store_path,
            )
            return []
        except Exception:
            logger.warning(
                "Vertex AI Search failed for tenant=%s", tenant_id, exc_info=True
            )
            return []
