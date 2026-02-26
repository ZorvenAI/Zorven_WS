"""Tests for PipelineComposer — dynamic pipeline composition."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.nodes.internal.pipeline_composer import (
    NODE_CATALOG,
    NODE_CATALOG_MAP,
    PipelineComposer,
    _build_compose_tool,
    _build_system_prompt,
)
from app.state.schema import AgentState


def _base_state(**overrides) -> AgentState:
    state: AgentState = {
        "job_id": "test-job",
        "tenant_id": "1",
        "input_prompt": "Analyze brand positioning for Acme Corp",
        "input_context": {"company_id": 42},
        "tenant_context": {"tenant_id": "1"},
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


# ── Catalog and tool generation tests ──


class TestNodeCatalog:
    def test_catalog_has_expected_nodes(self):
        ids = {n["id"] for n in NODE_CATALOG}
        expected = {
            "default_agent",
            "web_research",
            "blog_author",
            "social_promoter",
            "valuation_logic",
            "gap_analyzer",
        }
        assert expected == ids

    def test_catalog_map_matches_catalog(self):
        assert len(NODE_CATALOG_MAP) == len(NODE_CATALOG)
        for entry in NODE_CATALOG:
            assert entry["id"] in NODE_CATALOG_MAP

    def test_all_entries_have_required_fields(self):
        for entry in NODE_CATALOG:
            assert "id" in entry
            assert "type" in entry
            assert "description" in entry
            assert "output_key" in entry
            if entry["type"] == "external":
                assert "url" in entry
            elif entry["type"] == "internal":
                assert "handler" in entry


class TestToolGeneration:
    def test_build_compose_tool_includes_all_node_ids(self):
        tool = _build_compose_tool(NODE_CATALOG)
        decl = tool["function_declarations"][0]
        enum_values = decl["parameters"]["properties"]["node_ids"]["items"]["enum"]
        for entry in NODE_CATALOG:
            assert entry["id"] in enum_values
        assert "manager" in enum_values

    def test_build_system_prompt_includes_all_nodes(self):
        prompt = _build_system_prompt(NODE_CATALOG)
        for entry in NODE_CATALOG:
            assert entry["id"] in prompt
        assert "manager" in prompt


# ── Gemini composition tests ──


class TestGeminiComposition:
    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_rag_blog_social_prompt(self, mock_settings):
        """Gemini returns compose_pipeline for RAG+blog+social prompt."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        composer = PipelineComposer()

        # Mock the Gemini response
        mock_fn_call = MagicMock()
        mock_fn_call.name = "compose_pipeline"
        mock_fn_call.args = {
            "node_ids": [
                "default_agent",
                "blog_author",
                "social_promoter",
                "manager",
            ]
        }

        mock_part = MagicMock()
        mock_part.function_call = mock_fn_call

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        with patch(
            "google.generativeai.GenerativeModel"
        ) as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(
                return_value=mock_response
            )
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt=(
                    "Write a blog by reviewing the AN_EXPLORATORY_STUDY "
                    "document from the vertedx store and post on LinkedIn "
                    "as a scheduled task"
                )
            )
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        manifest = result["_composed_manifest"]
        node_ids = [n["id"] for n in manifest["nodes"]]
        assert node_ids == [
            "default_agent",
            "blog_author",
            "social_promoter",
            "manager",
        ]

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_web_blog_prompt(self, mock_settings):
        """Gemini returns compose_pipeline for plain blog prompt."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        composer = PipelineComposer()

        mock_fn_call = MagicMock()
        mock_fn_call.name = "compose_pipeline"
        mock_fn_call.args = {
            "node_ids": ["web_research", "blog_author", "manager"]
        }

        mock_part = MagicMock()
        mock_part.function_call = mock_fn_call

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        with patch(
            "google.generativeai.GenerativeModel"
        ) as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(
                return_value=mock_response
            )
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt="Write a blog about Tesla and post it online"
            )
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        node_ids = [n["id"] for n in result["_composed_manifest"]["nodes"]]
        assert node_ids == ["web_research", "blog_author", "manager"]

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_iso_valuation_prompt(self, mock_settings):
        """Gemini returns compose_pipeline for ISO valuation prompt."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        composer = PipelineComposer()

        mock_fn_call = MagicMock()
        mock_fn_call.name = "compose_pipeline"
        mock_fn_call.args = {
            "node_ids": ["web_research", "valuation_logic", "manager"]
        }

        mock_part = MagicMock()
        mock_part.function_call = mock_fn_call

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        with patch(
            "google.generativeai.GenerativeModel"
        ) as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(
                return_value=mock_response
            )
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt="Analyze the brand equity of Nike"
            )
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        node_ids = [n["id"] for n in result["_composed_manifest"]["nodes"]]
        assert node_ids == ["web_research", "valuation_logic", "manager"]

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_gemini_error_falls_back_to_keywords(self, mock_settings):
        """Gemini error → falls back to keyword matching."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        composer = PipelineComposer()

        with patch(
            "google.generativeai.GenerativeModel"
        ) as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(
                side_effect=Exception("API error")
            )
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt="Write a blog about Tesla and post on linkedin"
            )
            result = await composer.compose(state)

        assert "resolved_manifest_id" in result
        assert result["resolved_manifest_id"] == "social-promotion"

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_no_api_key_falls_back_to_keywords(self, mock_settings):
        """No Gemini API key → keyword fallback."""
        mock_settings.GOOGLE_API_KEY = ""

        composer = PipelineComposer()
        state = _base_state(
            input_prompt="ISO brand equity valuation"
        )
        result = await composer.compose(state)

        assert "resolved_manifest_id" in result
        assert result["resolved_manifest_id"] == "iso-brand-equity"


# ── Validation tests ──


class TestNodeIdValidation:
    def test_filters_unknown_ids(self):
        composer = PipelineComposer()
        result = composer._validate_node_ids(
            ["web_research", "unknown_node", "manager"]
        )
        assert result == ["web_research", "manager"]

    def test_appends_manager_if_missing(self):
        composer = PipelineComposer()
        result = composer._validate_node_ids(["web_research", "blog_author"])
        assert result == ["web_research", "blog_author", "manager"]

    def test_moves_manager_to_end(self):
        composer = PipelineComposer()
        result = composer._validate_node_ids(
            ["manager", "web_research", "blog_author"]
        )
        assert result[-1] == "manager"
        assert "web_research" in result
        assert "blog_author" in result

    def test_all_unknown_returns_none(self):
        composer = PipelineComposer()
        result = composer._validate_node_ids(["unknown1", "unknown2"])
        assert result is None

    def test_empty_list_returns_none(self):
        composer = PipelineComposer()
        result = composer._validate_node_ids([])
        assert result is None


# ── Manifest building tests ──


class TestManifestBuilding:
    def test_builds_correct_nodes(self):
        composer = PipelineComposer()
        manifest = composer._build_manifest(
            ["default_agent", "blog_author", "social_promoter", "manager"]
        )

        nodes = manifest["nodes"]
        assert len(nodes) == 4
        assert nodes[0]["id"] == "default_agent"
        assert nodes[0]["type"] == "internal"
        assert nodes[0]["handler"] == "DefaultAgentNode"
        assert nodes[1]["id"] == "blog_author"
        assert nodes[1]["type"] == "external"
        assert nodes[1]["url"] == "http://content-agent-svc:8050/v1/execute"
        assert nodes[3]["id"] == "manager"
        assert nodes[3]["handler"] == "ManagerNode"

    def test_builds_sequential_edges(self):
        composer = PipelineComposer()
        manifest = composer._build_manifest(
            ["web_research", "blog_author", "manager"]
        )

        edges = manifest["edges"]
        assert edges == [
            ["web_research", "blog_author"],
            ["blog_author", "manager"],
        ]

    def test_includes_global_config(self):
        composer = PipelineComposer()
        manifest = composer._build_manifest(["web_research", "manager"])
        assert manifest["global_config"]["model"] == "gemini-2.0-flash"
        assert manifest["global_config"]["temperature"] == 0.7

    def test_includes_node_config(self):
        composer = PipelineComposer()
        manifest = composer._build_manifest(
            ["blog_author", "manager"]
        )
        blog_node = manifest["nodes"][0]
        assert blog_node["config"]["output_format"] == "markdown"


# ── Keyword fallback tests ──


class TestKeywordFallback:
    async def test_rag_blog_social_prompt(self):
        """RAG+blog+social prompt → rag-blog-social."""
        composer = PipelineComposer()
        result = composer._keyword_fallback(
            _base_state(
                input_prompt=(
                    "Write a blog by reviewing the document from the "
                    "vertedx store and post on LinkedIn as a scheduled task"
                )
            )
        )
        assert result == "rag-blog-social"

    async def test_plain_blog_prompt(self):
        """Plain blog prompt → blog-authoring."""
        composer = PipelineComposer()
        result = composer._keyword_fallback(
            _base_state(input_prompt="write a blog about Tesla")
        )
        assert result == "blog-authoring"

    async def test_social_promotion_prompt(self):
        """Blog + social without RAG → social-promotion."""
        composer = PipelineComposer()
        result = composer._keyword_fallback(
            _base_state(
                input_prompt="Write a blog about Tesla and post on LinkedIn"
            )
        )
        assert result == "social-promotion"

    async def test_rag_blog_social_beats_social_promotion(self):
        """RAG+blog+social scores higher than social-promotion."""
        prompt = (
            "Can you write a blog post by reviewing the "
            "AN_EXPLORATORY_STUDY_ON_BRAND_MANAGEMENT document from "
            "the vertedx store and post that blog in LinkedIn as a "
            "scheduled task?"
        )
        composer = PipelineComposer()
        result = composer._keyword_fallback(_base_state(input_prompt=prompt))
        assert result == "rag-blog-social"

    async def test_respects_available_manifests(self):
        """Keyword fallback respects available_manifests filter."""
        composer = PipelineComposer()
        result = composer._keyword_fallback(
            _base_state(
                input_prompt="ISO brand equity valuation",
                available_manifests=[
                    {
                        "pipeline_id": "brand-analysis",
                        "name": "BA",
                        "description": "",
                    }
                ],
            )
        )
        assert result == "brand-analysis"
