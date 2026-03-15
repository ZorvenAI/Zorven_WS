"""Tests for PipelineComposer — 3-tier dynamic pipeline composition."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.nodes.internal.pipeline_composer import (
    NODE_CATALOG,
    NODE_CATALOG_MAP,
    PipelineComposer,
    _build_compose_tool,
    _build_system_prompt,
    _build_classify_system_prompt,
    _PIPELINE_DESCRIPTIONS,
    _FEW_SHOT_EXAMPLES,
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
            "rag_uploader",
            "odoo_worker",
            "odoo_sales_crm",
            "odoo_finance",
            "odoo_inventory",
            "odoo_hr",
            "odoo_marketing",
            "odoo_manufacturing",
            "market_research",
            "competitor_intelligence",
            "audience_persona",
            "trend_cultural",
            "voice_of_customer",
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

    def test_build_compose_tool_includes_dependencies(self):
        tool = _build_compose_tool(NODE_CATALOG)
        decl = tool["function_declarations"][0]
        props = decl["parameters"]["properties"]
        assert "dependencies" in props
        assert props["dependencies"]["type"] == "string"

    def test_build_system_prompt_includes_all_nodes(self):
        prompt = _build_system_prompt(NODE_CATALOG)
        for entry in NODE_CATALOG:
            assert entry["id"] in prompt
        assert "manager" in prompt


# ── Gemini composition tests (Tier 1) ──


def _mock_gemini_response(fn_name: str, args: dict) -> MagicMock:
    """Helper to build a mock Gemini response with a function call."""
    mock_fn_call = MagicMock()
    mock_fn_call.name = fn_name
    mock_fn_call.args = args

    mock_part = MagicMock()
    mock_part.function_call = mock_fn_call

    mock_response = MagicMock()
    mock_response.parts = [mock_part]
    return mock_response


class TestGeminiComposition:
    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_rag_blog_social_prompt(self, mock_settings):
        """Gemini returns compose_pipeline for RAG+blog+social prompt."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 1
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "compose_pipeline",
            {
                "node_ids": [
                    "default_agent",
                    "blog_author",
                    "social_promoter",
                    "manager",
                ]
            },
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
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
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 1
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "compose_pipeline",
            {"node_ids": ["web_research", "blog_author", "manager"]},
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
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
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 1
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "compose_pipeline",
            {"node_ids": ["web_research", "valuation_logic", "manager"]},
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(input_prompt="Analyze the brand equity of Nike")
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        node_ids = [n["id"] for n in result["_composed_manifest"]["nodes"]]
        assert node_ids == ["web_research", "valuation_logic", "manager"]

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_gemini_error_falls_to_tier2(self, mock_settings):
        """Gemini Tier 1 error → falls to Tier 2 LLM classification."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 0
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        # Tier 2 response
        tier2_response = _mock_gemini_response(
            "select_pipeline",
            {"pipeline_id": "social-promotion", "reason": "LinkedIn mentioned"},
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("API error")
            return tier2_response

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(side_effect=side_effect)
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt="Write a blog about Tesla and post on linkedin"
            )
            result = await composer.compose(state)

        assert "resolved_manifest_id" in result
        assert result["resolved_manifest_id"] == "social-promotion"

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_no_api_key_falls_back_to_keywords(self, mock_settings):
        """No Gemini API key → keyword fallback (Tier 3)."""
        mock_settings.GOOGLE_API_KEY = ""

        composer = PipelineComposer()
        state = _base_state(input_prompt="ISO brand equity valuation")
        result = await composer.compose(state)

        assert "resolved_manifest_id" in result
        assert result["resolved_manifest_id"] == "iso-brand-equity"


# ── Enhanced Gemini Composition tests (Tier 1 enrichment) ──


class TestEnhancedGeminiComposition:
    def test_gemini_receives_chat_history(self):
        """User message includes chat history when available."""
        composer = PipelineComposer()
        state = _base_state(
            input_prompt="now write a blog about it",
            input_context={
                "company_id": 42,
                "chat_history": [
                    {"role": "user", "content": "Tell me about Tesla"},
                    {"role": "assistant", "content": "Tesla is an EV company."},
                    {"role": "user", "content": "What about their brand?"},
                ],
            },
        )
        msg = composer._build_user_message(state)
        assert "Recent conversation:" in msg
        assert "Tell me about Tesla" in msg
        assert "Tesla is an EV company" in msg
        assert "Current request:" in msg
        assert "now write a blog about it" in msg

    def test_enriched_system_prompt_includes_company(self):
        """System prompt includes company context."""
        composer = PipelineComposer()
        state = _base_state(
            input_context={
                "company_id": 42,
                "company_name": "Acme Corp",
                "sector": "Technology",
                "brand_voice": "Professional",
            }
        )
        prompt = composer._enrich_system_prompt(state)
        assert "Acme Corp" in prompt
        assert "Technology" in prompt
        assert "Professional" in prompt

    def test_enriched_system_prompt_includes_rag_hint(self):
        """System prompt includes RAG hint when needs_rag is True."""
        composer = PipelineComposer()
        state = _base_state(input_context={"company_id": 42, "needs_rag": True})
        prompt = composer._enrich_system_prompt(state)
        assert "default_agent" in prompt
        assert "uploaded documents" in prompt

    def test_enriched_system_prompt_includes_few_shot_examples(self):
        """System prompt includes few-shot examples."""
        composer = PipelineComposer()
        state = _base_state()
        prompt = composer._enrich_system_prompt(state)
        assert "Write a blog about Tesla" in prompt
        assert "blog_author" in prompt

    def test_no_chat_history_returns_plain_prompt(self):
        """Without chat history, returns just the sanitized prompt."""
        composer = PipelineComposer()
        state = _base_state(input_prompt="Write a blog about Tesla")
        msg = composer._build_user_message(state)
        assert msg == "Write a blog about Tesla"
        assert "Recent conversation:" not in msg

    def test_enriched_system_prompt_includes_manifest_reference(self):
        """System prompt includes available manifest descriptions."""
        composer = PipelineComposer()
        state = _base_state(
            available_manifests=[
                {
                    "pipeline_id": "brand-analysis",
                    "name": "Brand Analysis",
                    "description": "Full brand analysis",
                },
                {
                    "pipeline_id": "blog-authoring",
                    "name": "Blog Authoring",
                    "description": "Write blog posts",
                },
            ]
        )
        prompt = composer._enrich_system_prompt(state)
        assert "brand-analysis" in prompt
        assert "Full brand analysis" in prompt
        assert "blog-authoring" in prompt


# ── Gemini Retry tests ──


class TestGeminiRetry:
    @patch("app.nodes.internal.pipeline_composer.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_retries_once_on_failure(self, mock_settings, mock_sleep):
        """Verify retry + sleep on first failure, then re-raise."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 1
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 2.0

        composer = PipelineComposer()

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(
                side_effect=Exception("API error")
            )
            mock_model_class.return_value = mock_model

            try:
                state = _base_state(input_prompt="test prompt")
                await composer._gemini_compose(state)
            except Exception:
                pass

            # 2 calls: initial + 1 retry
            assert mock_model.generate_content_async.call_count == 2
            # 1 sleep call between attempts
            mock_sleep.assert_called_once_with(2.0)

    @patch("app.nodes.internal.pipeline_composer.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_succeeds_on_retry(self, mock_settings, mock_sleep):
        """First call fails, second succeeds."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 1
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 1.0

        composer = PipelineComposer()

        success_response = _mock_gemini_response(
            "compose_pipeline",
            {"node_ids": ["web_research", "blog_author", "manager"]},
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("API error")
            return success_response

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(side_effect=side_effect)
            mock_model_class.return_value = mock_model

            state = _base_state(input_prompt="Write a blog about Tesla")
            result = await composer._gemini_compose(state)

        node_ids, sub_tasks, deps = result
        assert node_ids == ["web_research", "blog_author", "manager"]
        assert sub_tasks == {}
        assert deps == {}
        mock_sleep.assert_called_once_with(1.0)


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
        result = composer._validate_node_ids(["manager", "web_research", "blog_author"])
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
        manifest = composer._build_manifest(["web_research", "blog_author", "manager"])

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
        manifest = composer._build_manifest(["blog_author", "manager"])
        blog_node = manifest["nodes"][0]
        assert blog_node["config"]["output_format"] == "markdown"


# ── Keyword fallback tests (Tier 3) ──


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
            _base_state(input_prompt="Write a blog about Tesla and post on LinkedIn")
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

    async def test_default_is_general_chat(self):
        """Unrecognized prompts default to general-chat."""
        composer = PipelineComposer()
        result = composer._keyword_fallback(
            _base_state(input_prompt="xyzzy foobar baz")
        )
        assert result == "general-chat"

    async def test_needs_rag_boosts_rag_pipelines(self):
        """needs_rag flag boosts RAG pipeline scores."""
        composer = PipelineComposer()
        result = composer._keyword_fallback(
            _base_state(
                input_prompt="write a blog about this",
                input_context={"company_id": 42, "needs_rag": True},
            )
        )
        assert result == "rag-blog-authoring"


# ── LLM Classification Fallback tests (Tier 2) ──


class TestLLMClassifyFallback:
    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_selects_social_promotion(self, mock_settings):
        """Tier 2 correctly selects social-promotion."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "select_pipeline",
            {
                "pipeline_id": "social-promotion",
                "reason": "User wants to post on LinkedIn",
            },
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(input_prompt="Post our latest update on LinkedIn")
            result = await composer._llm_classify_fallback(state)

        assert result == "social-promotion"

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_returns_none_on_invalid_response(self, mock_settings):
        """Returns None when LLM returns invalid pipeline_id."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "select_pipeline",
            {
                "pipeline_id": "nonexistent-pipeline",
                "reason": "test",
            },
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(input_prompt="test")
            result = await composer._llm_classify_fallback(state)

        assert result is None

    def test_uses_needs_rag_hint(self):
        """Classify system prompt includes RAG hint when needs_rag is True."""
        prompt = _build_classify_system_prompt(needs_rag=True)
        assert "uploaded documents" in prompt
        assert "rag-blog-social" in prompt

    def test_no_rag_hint_without_flag(self):
        """Classify system prompt omits RAG hint when needs_rag is False."""
        prompt = _build_classify_system_prompt(needs_rag=False)
        assert "uploaded documents" not in prompt.split("Routing rules:")[1]

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_returns_none_when_no_function_call(self, mock_settings):
        """Returns None when Gemini doesn't return a function call."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"

        composer = PipelineComposer()

        mock_response = MagicMock()
        mock_part = MagicMock()
        mock_part.function_call = None
        mock_response.parts = [mock_part]

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(input_prompt="test")
            result = await composer._llm_classify_fallback(state)

        assert result is None


# ── Full fallback chain tests ──


class TestFullFallbackChain:
    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_tier1_success_skips_tier2_and_tier3(self, mock_settings):
        """Tier 1 success → returns _composed_manifest, no Tier 2/3."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 0
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "compose_pipeline",
            {"node_ids": ["web_research", "blog_author", "manager"]},
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(input_prompt="Write a blog about Tesla")
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        # Only 1 Gemini call (Tier 1), no Tier 2 call
        assert mock_model.generate_content_async.call_count == 1

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_tier1_fails_tier2_succeeds(self, mock_settings):
        """Tier 1 fails → Tier 2 selects a pipeline."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 0
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        tier2_response = _mock_gemini_response(
            "select_pipeline",
            {"pipeline_id": "blog-authoring", "reason": "Blog request"},
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Tier 1 API error")
            return tier2_response

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(side_effect=side_effect)
            mock_model_class.return_value = mock_model

            state = _base_state(input_prompt="Write a blog about Tesla")
            result = await composer.compose(state)

        assert result == {"resolved_manifest_id": "blog-authoring"}

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_tier1_and_tier2_fail_falls_to_tier3(self, mock_settings):
        """Both Tier 1 and Tier 2 fail → Tier 3 keyword matching."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 0
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
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
    async def test_no_api_key_skips_to_tier3(self, mock_settings):
        """No API key → skip Tier 1 and 2, go straight to Tier 3."""
        mock_settings.GOOGLE_API_KEY = ""

        composer = PipelineComposer()
        state = _base_state(input_prompt="competitor benchmarking analysis")
        result = await composer.compose(state)

        assert result == {"resolved_manifest_id": "competitor-intelligence"}


# ── Classify system prompt tests ──


class TestClassifySystemPrompt:
    def test_includes_all_pipeline_ids(self):
        prompt = _build_classify_system_prompt()
        for p in _PIPELINE_DESCRIPTIONS:
            assert p["id"] in prompt

    def test_includes_routing_rules(self):
        prompt = _build_classify_system_prompt()
        assert "social-promotion" in prompt
        assert "blog-authoring" in prompt
        assert "iso-brand-equity" in prompt

    def test_includes_email_marketing_keywords(self):
        prompt = _build_classify_system_prompt()
        assert "email marketing" in prompt
        assert "newsletters" in prompt


# ── Persona-specific Odoo catalog tests ──


class TestOdooCatalogEntries:
    def test_persona_specific_nodes_have_persona_hint(self):
        persona_nodes = {
            "odoo_sales_crm": "sales_manager",
            "odoo_finance": "accountant",
            "odoo_inventory": "warehouse_manager",
            "odoo_hr": "hr_manager",
            "odoo_marketing": "marketing_manager",
            "odoo_manufacturing": "manufacturing_supervisor",
        }
        for node_id, expected_hint in persona_nodes.items():
            entry = NODE_CATALOG_MAP[node_id]
            assert entry["config"]["persona_hint"] == expected_hint

    def test_persona_nodes_share_odoo_worker_url(self):
        base_url = NODE_CATALOG_MAP["odoo_worker"]["url"]
        for node_id in [
            "odoo_sales_crm",
            "odoo_finance",
            "odoo_inventory",
            "odoo_hr",
            "odoo_marketing",
            "odoo_manufacturing",
        ]:
            assert NODE_CATALOG_MAP[node_id]["url"] == base_url

    def test_generic_odoo_worker_has_no_persona_hint(self):
        assert "persona_hint" not in NODE_CATALOG_MAP["odoo_worker"]["config"]


# ── Sub-task manifest building tests ──


class TestSubTaskManifestBuilding:
    def test_build_manifest_with_sub_tasks(self):
        composer = PipelineComposer()
        sub_tasks = {
            "odoo_sales_crm": "Find customers and product info",
            "odoo_marketing": "Create email campaign",
        }
        manifest = composer._build_manifest(
            ["odoo_sales_crm", "odoo_marketing", "manager"],
            sub_tasks=sub_tasks,
        )
        nodes = manifest["nodes"]
        # Sales node gets both persona_hint and sub_task
        sales_node = nodes[0]
        assert sales_node["config"]["persona_hint"] == "sales_manager"
        assert sales_node["config"]["sub_task"] == "Find customers and product info"
        # Marketing node gets both persona_hint and sub_task
        marketing_node = nodes[1]
        assert marketing_node["config"]["persona_hint"] == "marketing_manager"
        assert marketing_node["config"]["sub_task"] == "Create email campaign"

    def test_build_manifest_without_sub_tasks(self):
        composer = PipelineComposer()
        manifest = composer._build_manifest(
            ["odoo_sales_crm", "manager"],
        )
        sales_node = manifest["nodes"][0]
        assert sales_node["config"]["persona_hint"] == "sales_manager"
        assert "sub_task" not in sales_node["config"]

    def test_sub_tasks_only_applied_to_matching_nodes(self):
        composer = PipelineComposer()
        sub_tasks = {"odoo_sales_crm": "Find products"}
        manifest = composer._build_manifest(
            ["odoo_sales_crm", "odoo_marketing", "manager"],
            sub_tasks=sub_tasks,
        )
        marketing_node = manifest["nodes"][1]
        assert "sub_task" not in marketing_node["config"]


# ── Multi-worker Gemini composition tests ──


class TestMultiWorkerComposition:
    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_multi_worker_email_campaign(self, mock_settings):
        """Gemini returns multi-worker pipeline for email campaign."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 0
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "compose_pipeline",
            {
                "node_ids": ["odoo_sales_crm", "odoo_marketing", "manager"],
                "sub_tasks": {
                    "odoo_sales_crm": "Find product and customer list",
                    "odoo_marketing": "Create email campaign",
                },
            },
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt="Launch an email campaign for Conference Chair"
            )
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        manifest = result["_composed_manifest"]
        node_ids = [n["id"] for n in manifest["nodes"]]
        assert node_ids == ["odoo_sales_crm", "odoo_marketing", "manager"]
        # Verify sub_tasks are merged into config
        sales_node = manifest["nodes"][0]
        assert sales_node["config"]["sub_task"] == "Find product and customer list"
        assert sales_node["config"]["persona_hint"] == "sales_manager"

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_multi_worker_sales_invoice(self, mock_settings):
        """Gemini returns multi-worker pipeline for sales + invoice."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 0
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "compose_pipeline",
            {
                "node_ids": ["odoo_sales_crm", "odoo_finance", "manager"],
                "sub_tasks": {
                    "odoo_sales_crm": "Create sales order",
                    "odoo_finance": "Generate invoice",
                },
            },
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt="Create a sales order and generate the invoice"
            )
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        manifest = result["_composed_manifest"]
        node_ids = [n["id"] for n in manifest["nodes"]]
        assert node_ids == ["odoo_sales_crm", "odoo_finance", "manager"]


# ── Dependency-based manifest building tests ──


class TestDependencyManifestBuilding:
    def test_build_manifest_with_dependencies(self):
        """Dependencies dict generates correct edges (not sequential)."""
        composer = PipelineComposer()
        deps = {
            "odoo_sales_crm": [],
            "odoo_inventory": [],
            "manager": ["odoo_sales_crm", "odoo_inventory"],
        }
        manifest = composer._build_manifest(
            ["odoo_sales_crm", "odoo_inventory", "manager"],
            dependencies=deps,
        )
        edges = manifest["edges"]
        assert ["odoo_sales_crm", "manager"] in edges
        assert ["odoo_inventory", "manager"] in edges
        # No edge between the two parallel nodes
        assert ["odoo_sales_crm", "odoo_inventory"] not in edges
        assert ["odoo_inventory", "odoo_sales_crm"] not in edges
        assert len(edges) == 2

    def test_build_manifest_dependencies_fallback_sequential(self):
        """Empty dependencies → sequential edges (backward compat)."""
        composer = PipelineComposer()
        manifest = composer._build_manifest(
            ["odoo_sales_crm", "odoo_inventory", "manager"],
            dependencies={},
        )
        edges = manifest["edges"]
        assert edges == [
            ["odoo_sales_crm", "odoo_inventory"],
            ["odoo_inventory", "manager"],
        ]

    def test_build_manifest_dependencies_none_sequential(self):
        """None dependencies → sequential edges (backward compat)."""
        composer = PipelineComposer()
        manifest = composer._build_manifest(
            ["odoo_sales_crm", "odoo_inventory", "manager"],
            dependencies=None,
        )
        edges = manifest["edges"]
        assert edges == [
            ["odoo_sales_crm", "odoo_inventory"],
            ["odoo_inventory", "manager"],
        ]

    def test_dependencies_auto_wire_manager(self):
        """Manager not in dependencies → auto-wired from all others."""
        composer = PipelineComposer()
        deps = {
            "odoo_sales_crm": [],
            "odoo_inventory": [],
        }
        manifest = composer._build_manifest(
            ["odoo_sales_crm", "odoo_inventory", "manager"],
            dependencies=deps,
        )
        edges = manifest["edges"]
        assert ["odoo_sales_crm", "manager"] in edges
        assert ["odoo_inventory", "manager"] in edges

    def test_dependencies_with_sub_tasks(self):
        """Dependencies + sub_tasks are combined correctly."""
        composer = PipelineComposer()
        deps = {
            "odoo_hr": [],
            "odoo_inventory": [],
            "manager": ["odoo_hr", "odoo_inventory"],
        }
        sub_tasks = {
            "odoo_hr": "Get employee list",
            "odoo_inventory": "Check stock levels",
        }
        manifest = composer._build_manifest(
            ["odoo_hr", "odoo_inventory", "manager"],
            sub_tasks=sub_tasks,
            dependencies=deps,
        )
        # Edges are dependency-based
        assert ["odoo_hr", "manager"] in manifest["edges"]
        assert ["odoo_inventory", "manager"] in manifest["edges"]
        # Sub-tasks are applied
        hr_node = manifest["nodes"][0]
        assert hr_node["config"]["sub_task"] == "Get employee list"


# ── Gemini composition with dependencies tests ──


class TestGeminiComposeWithDependencies:
    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_gemini_compose_returns_dependencies(self, mock_settings):
        """Gemini returns dependencies for parallel execution."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 0
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "compose_pipeline",
            {
                "node_ids": ["odoo_sales_crm", "odoo_inventory", "manager"],
                "sub_tasks": {},
                "dependencies": {
                    "odoo_sales_crm": "",
                    "odoo_inventory": "",
                    "manager": "odoo_sales_crm,odoo_inventory",
                },
            },
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt="Check inventory and sales pipeline status"
            )
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        manifest = result["_composed_manifest"]
        edges = manifest["edges"]
        # Parallel: sales_crm→manager, inventory→manager
        assert ["odoo_sales_crm", "manager"] in edges
        assert ["odoo_inventory", "manager"] in edges
        assert len(edges) == 2

    @patch("app.nodes.internal.pipeline_composer.settings")
    async def test_gemini_compose_no_dependencies_fallback(self, mock_settings):
        """Gemini returns no dependencies → sequential edges."""
        mock_settings.GOOGLE_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_COMPOSE_MAX_RETRIES = 0
        mock_settings.GEMINI_COMPOSE_RETRY_DELAY = 0.0

        composer = PipelineComposer()

        mock_response = _mock_gemini_response(
            "compose_pipeline",
            {
                "node_ids": [
                    "odoo_sales_crm",
                    "odoo_finance",
                    "manager",
                ],
            },
        )

        with patch("google.generativeai.GenerativeModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_model_class.return_value = mock_model

            state = _base_state(
                input_prompt="Create a sales order and generate invoice"
            )
            result = await composer.compose(state)

        assert "_composed_manifest" in result
        manifest = result["_composed_manifest"]
        edges = manifest["edges"]
        # Sequential fallback
        assert edges == [
            ["odoo_sales_crm", "odoo_finance"],
            ["odoo_finance", "manager"],
        ]
