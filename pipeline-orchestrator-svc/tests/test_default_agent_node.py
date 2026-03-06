"""Tests for DefaultAgentNode — RAG specialist with Gemini synthesis."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.nodes.internal.default_agent_node import DefaultAgentNode
from app.nodes.tools.vertex_search_tool import SearchChunk
from app.state.schema import AgentState


def _base_state(**overrides) -> AgentState:
    state: AgentState = {
        "job_id": "test-job",
        "tenant_id": "1",
        "input_prompt": "Summarize the annual report",
        "input_context": {"company_id": 42},
        "tenant_context": {"tenant_id": "1", "rag_data_store_id": "ds-test"},
        "global_config": {},
        "callback_url": "http://localhost:8001/callback/",
        "available_manifests": None,
        "resolved_manifest_id": None,
        "node_outputs": {},
        "progress": {},
        "result_data": None,
        "error": None,
        "cancelled": False,
    }
    state.update(overrides)
    return state


_MOCK_CHUNKS = [
    SearchChunk(
        text="Revenue grew 15% year-over-year to $5.2B.",
        source_uri="gs://bucket/annual-report.pdf",
        source_name="Annual Report 2024",
        relevance_score=0.95,
    ),
    SearchChunk(
        text="Operating margin improved to 22%.",
        source_uri="gs://bucket/financials.pdf",
        source_name="Financial Summary",
        relevance_score=0.88,
    ),
]


class TestDefaultAgentNode:
    """Tests for DefaultAgentNode."""

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    @patch.object(
        DefaultAgentNode,
        "_DefaultAgentNode__init_search_tool",
        create=True,
    )
    async def test_returns_result_data_with_sources(
        self, mock_init, mock_genai, mock_trace
    ):
        """Full flow with mocked VertexSearchTool + Gemini."""
        mock_trace.return_value = None

        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = "The annual report shows strong growth."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=_MOCK_CHUNKS)

        result = await node(_base_state())

        assert "result_data" in result
        rd = result["result_data"]
        assert "summary" in rd
        assert rd["grounded"] is True
        assert len(rd["sources"]) == 2
        assert rd["sources"][0]["name"] == "Annual Report 2024"

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    async def test_empty_search_results_general_knowledge(self, mock_genai, mock_trace):
        """Fallback response when no documents found."""
        mock_trace.return_value = None

        mock_response = MagicMock()
        mock_response.text = "Based on general knowledge, brand equity is..."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=[])

        result = await node(_base_state())

        rd = result["result_data"]
        assert rd["grounded"] is False
        assert rd["sources"] == []

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    async def test_reads_chat_history(self, mock_genai, mock_trace):
        """Chat history passed to Gemini prompt."""
        mock_trace.return_value = None

        mock_response = MagicMock()
        mock_response.text = "Following up on our discussion..."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=[])

        chat_history = [
            {"role": "user", "content": "What is brand equity?"},
            {"role": "assistant", "content": "Brand equity is..."},
        ]
        state = _base_state(input_context={"chat_history": chat_history})
        result = await node(state)

        # Verify Gemini was called and prompt included history
        call_args = mock_model.generate_content_async.call_args
        prompt = call_args[0][0]
        assert "brand equity" in prompt.lower()

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    async def test_reads_tenant_context(self, mock_genai, mock_trace):
        """Tenant ID used for search scoping."""
        mock_trace.return_value = None

        mock_response = MagicMock()
        mock_response.text = "Tenant-scoped answer."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=[])

        state = _base_state(
            tenant_context={
                "tenant_id": "42",
                "rag_data_store_id": "custom-ds",
            }
        )
        await node(state)

        # Verify search was called with correct tenant_id
        node._search_tool.search.assert_called_once_with(
            query="Summarize the annual report",
            tenant_id="42",
            data_store_id="custom-ds",
        )

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    async def test_writes_to_node_outputs(self, mock_genai, mock_trace):
        """Output stored in node_outputs['default_agent']."""
        mock_trace.return_value = None

        mock_response = MagicMock()
        mock_response.text = "Test answer."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=[])

        result = await node(_base_state())

        assert "node_outputs" in result
        assert "default_agent" in result["node_outputs"]
        assert "summary" in result["node_outputs"]["default_agent"]

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    async def test_trace_events_emitted(self, mock_genai, mock_trace):
        """Kafka trace producer called with correct thought messages."""
        mock_trace.return_value = None

        mock_response = MagicMock()
        mock_response.text = "Answer."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=_MOCK_CHUNKS)

        await node(_base_state())

        # Should have 4 trace calls: pre-search, search, post-search, completion
        assert mock_trace.call_count == 4

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    async def test_gemini_failure_returns_search_only(self, mock_genai, mock_trace):
        """Graceful degradation when Gemini fails."""
        mock_trace.return_value = None

        # Make Gemini raise an exception
        mock_genai.configure.side_effect = Exception("API key invalid")

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=_MOCK_CHUNKS)

        result = await node(_base_state())

        rd = result["result_data"]
        # Should still return a result with search chunk info
        assert "summary" in rd
        assert "found some relevant information" in rd["summary"].lower() or (
            "couldn't" in rd["summary"].lower()
        )

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    @patch(
        "app.nodes.internal.default_agent_node.DefaultAgentNode._download_attachments"
    )
    async def test_attachment_files_passed_to_gemini(
        self, mock_download, mock_genai, mock_trace
    ):
        """Attachments from input_context are downloaded and sent to Gemini."""
        mock_trace.return_value = None
        mock_download.return_value = [
            ("report.pdf", b"PDF content here"),
        ]

        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "files/abc123"
        mock_genai.upload_file.return_value = mock_uploaded_file
        mock_genai.delete_file = MagicMock()

        mock_response = MagicMock()
        mock_response.text = "The report discusses quarterly earnings."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=[])

        state = _base_state(
            input_context={
                "attachments": [
                    {
                        "id": 1,
                        "file_name": "report.pdf",
                        "file_type": "document",
                        "gcs_bucket": "brand-automator",
                        "gcs_path": "_landing/1/abc_report.pdf",
                    }
                ],
            }
        )
        result = await node(state)

        rd = result["result_data"]
        assert rd["grounded"] is True
        # Attachment should appear in sources
        source_names = [s["name"] for s in rd["sources"]]
        assert "report.pdf" in source_names
        # Gemini should have been called with multimodal content (list)
        call_args = mock_model.generate_content_async.call_args
        content = call_args[0][0]
        assert isinstance(content, list)

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    async def test_no_attachments_no_download(self, mock_genai, mock_trace):
        """When no attachments in input_context, GCS download is not called."""
        mock_trace.return_value = None

        mock_response = MagicMock()
        mock_response.text = "Answer without attachments."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=[])

        state = _base_state(input_context={})
        result = await node(state)

        rd = result["result_data"]
        assert "summary" in rd
        # Gemini should have been called with a string (not list)
        call_args = mock_model.generate_content_async.call_args
        content = call_args[0][0]
        assert isinstance(content, str)

    @patch("app.nodes.internal.default_agent_node.DefaultAgentNode._emit_trace")
    @patch("app.nodes.internal.default_agent_node.genai")
    @patch(
        "app.nodes.internal.default_agent_node.DefaultAgentNode._download_attachments"
    )
    async def test_attachment_download_failure_non_fatal(
        self, mock_download, mock_genai, mock_trace
    ):
        """If GCS download fails, node still returns Vertex search results."""
        mock_trace.return_value = None
        mock_download.return_value = []  # Download failed, empty result

        mock_response = MagicMock()
        mock_response.text = "Based on indexed documents..."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.types.GenerationConfig = MagicMock()

        node = DefaultAgentNode()
        node._search_tool = MagicMock()
        node._search_tool.search = AsyncMock(return_value=_MOCK_CHUNKS)

        state = _base_state(
            input_context={
                "attachments": [
                    {
                        "id": 1,
                        "file_name": "missing.pdf",
                        "file_type": "document",
                        "gcs_bucket": "brand-automator",
                        "gcs_path": "_landing/1/missing.pdf",
                    }
                ],
            }
        )
        result = await node(state)

        rd = result["result_data"]
        assert rd["grounded"] is True
        # Should still have Vertex search sources
        assert len(rd["sources"]) >= 2
