"""Tests for VertexSearchTool — Vertex AI Discovery Engine search with caching."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.nodes.tools.vertex_search_tool import SearchChunk, VertexSearchTool


class TestVertexSearchTool:
    """Tests for VertexSearchTool."""

    @patch("app.nodes.tools.vertex_search_tool.get_redis")
    @patch("app.nodes.tools.vertex_search_tool.discoveryengine")
    async def test_search_returns_chunks(self, mock_de, mock_get_redis):
        """Mocked SearchServiceClient returns structured chunks."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # cache miss
        mock_get_redis.return_value = mock_redis

        # Build a mock search result
        mock_doc = MagicMock()
        mock_doc.name = "projects/p/locations/l/dataStores/ds/documents/doc1"
        mock_doc.derived_struct_data = {
            "snippets": [{"snippet": "Revenue grew 15% YoY."}],
            "link": "gs://bucket/report.pdf",
            "title": "Annual Report 2024",
        }
        mock_result = MagicMock()
        mock_result.document = mock_doc
        mock_result.relevance_score = 0.95

        mock_response = MagicMock()
        mock_response.results = [mock_result]

        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        mock_de.SearchServiceClient.return_value = mock_client
        mock_de.SearchRequest = MagicMock()

        tool = VertexSearchTool()
        chunks = await tool.search("revenue growth", "tenant-1")

        assert len(chunks) == 1
        assert chunks[0].text == "Revenue grew 15% YoY."
        assert chunks[0].source_name == "Annual Report 2024"
        assert chunks[0].source_uri == "gs://bucket/report.pdf"

    @patch("app.nodes.tools.vertex_search_tool.get_redis")
    async def test_search_with_redis_cache_hit(self, mock_get_redis):
        """Cached result returned without Vertex API call."""
        cached_data = [
            {
                "text": "Cached snippet",
                "source_uri": "gs://bucket/cached.pdf",
                "source_name": "Cached Doc",
                "relevance_score": 0.9,
            }
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(cached_data)
        mock_get_redis.return_value = mock_redis

        tool = VertexSearchTool()
        chunks = await tool.search("test query", "tenant-1")

        assert len(chunks) == 1
        assert chunks[0].text == "Cached snippet"
        assert chunks[0].source_name == "Cached Doc"

    @patch("app.nodes.tools.vertex_search_tool.get_redis")
    @patch("app.nodes.tools.vertex_search_tool.discoveryengine")
    async def test_search_with_redis_cache_miss(self, mock_de, mock_get_redis):
        """Result fetched from Vertex and cached in Redis."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # cache miss
        mock_get_redis.return_value = mock_redis

        mock_response = MagicMock()
        mock_response.results = []
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        mock_de.SearchServiceClient.return_value = mock_client
        mock_de.SearchRequest = MagicMock()

        tool = VertexSearchTool()
        await tool.search("test query", "tenant-1")

        # Verify cache write was attempted
        mock_redis.set.assert_called_once()

    def test_data_store_path_format(self):
        """Default data store path when no override is provided."""
        tool = VertexSearchTool()
        path = tool._get_data_store_path("42")
        assert "projects/brandsol-project" in path
        assert "locations/global" in path
        assert "collections/default_collection" in path
        assert "dataStores/prevision-rag-dev" in path

    def test_data_store_path_with_override(self):
        """Per-tenant data store ID is used directly when provided."""
        tool = VertexSearchTool()
        path = tool._get_data_store_path("42", data_store_id="prevision-creative-minds")
        assert "dataStores/prevision-creative-minds" in path

    def test_base_data_store_path_format(self):
        """Base data store path uses shared default."""
        tool = VertexSearchTool()
        path = tool._get_base_data_store_path()
        assert "projects/brandsol-project" in path
        assert "dataStores/prevision-rag-dev" in path

    @patch("app.nodes.tools.vertex_search_tool.get_redis")
    async def test_empty_query_returns_empty(self, mock_get_redis):
        """Empty query returns empty results without calling Vertex."""
        tool = VertexSearchTool()
        chunks = await tool.search("", "tenant-1")
        assert chunks == []
        chunks = await tool.search("   ", "tenant-1")
        assert chunks == []

    @patch("app.nodes.tools.vertex_search_tool.get_redis")
    @patch("app.nodes.tools.vertex_search_tool.discoveryengine")
    async def test_vertex_api_error_returns_empty(self, mock_de, mock_get_redis):
        """NotFound on data store returns empty results."""
        from google.api_core.exceptions import NotFound

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_client = MagicMock()
        mock_client.search.side_effect = NotFound("Data store not found")
        mock_de.SearchServiceClient.return_value = mock_client
        mock_de.SearchRequest = MagicMock()

        tool = VertexSearchTool()
        chunks = await tool.search("test", "tenant-999")
        assert chunks == []
        # Without a data_store_id override, primary and fallback are
        # the same path, so only one attempt is made.
        assert mock_client.search.call_count == 1

    @patch("app.nodes.tools.vertex_search_tool.get_redis")
    @patch("app.nodes.tools.vertex_search_tool.discoveryengine")
    async def test_vertex_api_error_tries_fallback(self, mock_de, mock_get_redis):
        """NotFound on per-tenant store falls back to shared default."""
        from google.api_core.exceptions import NotFound

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_client = MagicMock()
        mock_client.search.side_effect = NotFound("Data store not found")
        mock_de.SearchServiceClient.return_value = mock_client
        mock_de.SearchRequest = MagicMock()

        tool = VertexSearchTool()
        # With an override different from default, tries both paths
        chunks = await tool.search(
            "test", "tenant-999", data_store_id="prevision-creative-minds"
        )
        assert chunks == []
        assert mock_client.search.call_count == 2
