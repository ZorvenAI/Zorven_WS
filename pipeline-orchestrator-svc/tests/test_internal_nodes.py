"""Tests for all 7 internal node stubs."""

from app.nodes.internal.audience_node import AudienceNode
from app.nodes.internal.calendar_node import CalendarNode
from app.nodes.internal.default_agent_node import DefaultAgentNode
from app.nodes.internal.manager_node import ManagerNode
from app.nodes.internal.planner_node import PlannerNode
from app.nodes.internal.report_node import ReportNode
from app.nodes.internal.router_node import RouterNode, keyword_match, _stem
from app.nodes.internal.strategy_node import StrategyNode
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


class TestRouterNode:
    """Test intent routing via keyword matching."""

    async def test_default_resolves_general_chat(self):
        """No-keyword queries now default to general-chat (not brand-analysis)."""
        node = RouterNode()
        result = await node(_base_state(input_prompt="hello world"))
        assert result["resolved_manifest_id"] == "general-chat"

    async def test_keyword_iso_brand_equity(self):
        node = RouterNode()
        result = await node(_base_state(input_prompt="ISO brand equity valuation"))
        assert result["resolved_manifest_id"] == "iso-brand-equity"

    async def test_keyword_competitor_audit(self):
        node = RouterNode()
        result = await node(_base_state(input_prompt="competitor audit analysis"))
        assert result["resolved_manifest_id"] == "competitor-audit"

    async def test_keyword_content_strategy(self):
        node = RouterNode()
        result = await node(_base_state(input_prompt="content strategy calendar"))
        assert result["resolved_manifest_id"] == "content-strategy"

    async def test_keyword_general_chat_document(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="summarize the document I uploaded")
        )
        assert result["resolved_manifest_id"] == "general-chat"

    async def test_no_keyword_defaults_general_chat(self):
        """No-keyword queries now default to general-chat."""
        node = RouterNode()
        result = await node(_base_state(input_prompt="what is the weather"))
        assert result["resolved_manifest_id"] == "general-chat"

    async def test_respects_available_manifests(self):
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="ISO brand equity",
                available_manifests=[
                    {"pipeline_id": "brand-analysis", "name": "BA", "description": ""}
                ],
            )
        )
        # iso-brand-equity is not in available_manifests, falls back
        assert result["resolved_manifest_id"] == "brand-analysis"

    async def test_social_promotion_with_linkedin(self):
        """'write a blog and post it in LinkedIn' → social-promotion."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="write a blog on Brand planning and post it in LinkedIn"
            )
        )
        assert result["resolved_manifest_id"] == "social-promotion"

    async def test_social_promotion_with_twitter(self):
        node = RouterNode()
        result = await node(_base_state(input_prompt="share this on twitter"))
        assert result["resolved_manifest_id"] == "social-promotion"

    async def test_blog_without_social_routes_to_blog(self):
        """'write a blog about Tesla' without platform → blog-authoring."""
        node = RouterNode()
        result = await node(_base_state(input_prompt="write a blog about Tesla"))
        assert result["resolved_manifest_id"] == "blog-authoring"

    async def test_rag_blog_social_route(self):
        """RAG+blog+social prompt → rag-blog-social."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt=(
                    "Write a blog by reviewing the document from the "
                    "vertedx store and post on LinkedIn as a scheduled task"
                )
            )
        )
        assert result["resolved_manifest_id"] == "rag-blog-social"

    async def test_rag_blog_social_beats_social_promotion(self):
        """RAG+social prompt scores higher for rag-blog-social than social-promotion."""
        prompt = (
            "Can you write a blog post by reviewing the "
            "AN_EXPLORATORY_STUDY_ON_BRAND_MANAGEMENT document from "
            "the vertedx store and post that blog in LinkedIn as a "
            "scheduled task?"
        )
        node = RouterNode()
        result = await node(_base_state(input_prompt=prompt))
        assert result["resolved_manifest_id"] == "rag-blog-social"

    async def test_rag_blog_authoring_route(self):
        """RAG+blog without social → rag-blog-authoring."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt=(
                    "Write a blog based on the brand management "
                    "document from my knowledge base"
                )
            )
        )
        assert result["resolved_manifest_id"] == "rag-blog-authoring"


class TestSearchQueryExtraction:
    """Tests for DefaultAgentNode._extract_search_query."""

    def test_extracts_uppercase_document_name(self):
        prompt = (
            "Can you write a blog post by reviewing the "
            "AN_EXPLORATORY_STUDY_ON_BRAND_MANAGEMENT document from "
            "the vertedx store and post that blog in LinkedIn as a "
            "scheduled task?"
        )
        result = DefaultAgentNode._extract_search_query(prompt)
        assert result == "AN_EXPLORATORY_STUDY_ON_BRAND_MANAGEMENT"

    def test_extracts_shorter_uppercase_name(self):
        prompt = "Summarize the BRAND_GUIDELINES document from the store"
        result = DefaultAgentNode._extract_search_query(prompt)
        assert result == "BRAND_GUIDELINES"

    def test_picks_longest_match(self):
        prompt = "Compare ISO_10668 with AN_EXPLORATORY_STUDY_ON_BRAND_MANAGEMENT"
        result = DefaultAgentNode._extract_search_query(prompt)
        assert result == "AN_EXPLORATORY_STUDY_ON_BRAND_MANAGEMENT"

    def test_extracts_double_quoted_name(self):
        prompt = 'Review the "Brand Management Study" document'
        result = DefaultAgentNode._extract_search_query(prompt)
        assert result == "Brand Management Study"

    def test_extracts_single_quoted_name(self):
        prompt = "Summarize the 'quarterly report' from my files"
        result = DefaultAgentNode._extract_search_query(prompt)
        assert result == "quarterly report"

    def test_returns_full_prompt_when_no_doc_ref(self):
        prompt = "Tell me about brand management strategies"
        result = DefaultAgentNode._extract_search_query(prompt)
        assert result == prompt

    def test_ignores_short_uppercase_words(self):
        """Single uppercase words (AI, ISO) should not match — needs 2+ segments."""
        prompt = "Explain ISO brand equity valuation"
        result = DefaultAgentNode._extract_search_query(prompt)
        assert result == prompt


class TestStrategyNode:
    async def test_returns_strategy_data(self):
        node = StrategyNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        # StrategyNode writes under the "brand_strategist" key
        assert "brand_strategist" in outputs
        assert any(
            "positioning" in str(v) or "findings" in str(v) for v in outputs.values()
        )


class TestReportNode:
    async def test_returns_report_data(self):
        node = ReportNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        if outputs:
            assert any(
                "report" in str(v).lower() or "format" in str(v).lower()
                for v in outputs.values()
            )


class TestAudienceNode:
    async def test_returns_audience_data(self):
        node = AudienceNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        if outputs:
            assert any(
                "audience" in str(v).lower() or "primary" in str(v).lower()
                for v in outputs.values()
            )


class TestPlannerNode:
    async def test_returns_planner_data(self):
        node = PlannerNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        if outputs:
            assert any(
                "theme" in str(v).lower() or "content" in str(v).lower()
                for v in outputs.values()
            )


class TestCalendarNode:
    async def test_returns_calendar_data(self):
        node = CalendarNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        if outputs:
            assert any(
                "week" in str(v).lower() or "calendar" in str(v).lower()
                for v in outputs.values()
            )


class TestManagerNode:
    async def test_aggregates_node_outputs(self):
        node = ManagerNode()
        state = _base_state(
            node_outputs={
                "strategy": {
                    "findings": ["Strong brand recognition"],
                    "recommendations": ["Expand to new markets"],
                },
                "report": {
                    "findings": ["Market share at 15%"],
                },
            }
        )
        result = await node(state)
        assert "result_data" in result
        rd = result["result_data"]
        assert "summary" in rd
        assert "findings" in rd
        assert "recommendations" in rd
        assert "score" in rd
        assert len(rd["findings"]) >= 2
        assert len(rd["recommendations"]) >= 1

    async def test_empty_outputs_returns_defaults(self):
        node = ManagerNode()
        result = await node(_base_state(node_outputs={}))
        rd = result["result_data"]
        assert len(rd["findings"]) >= 1
        assert len(rd["recommendations"]) >= 1
        assert rd["score"] == 0

    async def test_skips_research_findings_when_processing_nodes_exist(self):
        """In multi-agent pipelines, research node findings are replaced
        with a brief source summary to avoid contradictory messages."""
        node = ManagerNode()
        state = _base_state(
            node_outputs={
                "default_agent": {
                    "findings": [
                        "I can help draft a blog post. However, I am unable "
                        "to directly schedule posts on LinkedIn."
                    ],
                    "recommendations": [],
                    "sources": [
                        {"name": "brand_study.pdf", "uri": "gs://bucket/doc.pdf"},
                    ],
                },
                "blog_author": {
                    "findings": ["Blog authored: Brand Management Trends"],
                    "recommendations": ["Review for accuracy"],
                },
                "social_promoter": {
                    "findings": ["Scheduled on: linkedin, twitter for 2026-02-27"],
                    "recommendations": [],
                },
            }
        )
        result = await node(state)
        rd = result["result_data"]
        # The contradictory DefaultAgentNode finding should NOT appear
        assert not any("unable" in f.lower() for f in rd["findings"])
        # A brief source summary should appear instead
        assert any("brand_study.pdf" in f for f in rd["findings"])
        # Downstream findings should be preserved
        assert any("Blog authored" in f for f in rd["findings"])
        assert any("Scheduled on" in f for f in rd["findings"])

    async def test_preserves_research_findings_in_standalone_chat(self):
        """In standalone chat (only research + manager), full findings
        are preserved since there are no downstream processing nodes."""
        node = ManagerNode()
        state = _base_state(
            node_outputs={
                "default_agent": {
                    "findings": ["The brand management study covers key topics..."],
                    "recommendations": ["Consider expanding the analysis"],
                    "sources": [
                        {"name": "brand_study.pdf", "uri": "gs://bucket/doc.pdf"},
                    ],
                },
            }
        )
        result = await node(state)
        rd = result["result_data"]
        # Full research findings should be preserved (no processing nodes)
        assert any("brand management study" in f for f in rd["findings"])
        assert any("expanding the analysis" in r for r in rd["recommendations"])

    async def test_web_research_also_summarised_in_pipeline(self):
        """web_research findings are also summarised when processing nodes exist."""
        node = ManagerNode()
        state = _base_state(
            node_outputs={
                "web_research": {
                    "findings": ["Found 10 articles about Tesla"],
                    "recommendations": [],
                    "sources": [
                        {"name": "Reuters", "uri": "https://reuters.com"},
                        {"name": "Bloomberg", "uri": "https://bloomberg.com"},
                    ],
                },
                "blog_author": {
                    "findings": ["Blog authored: Tesla Analysis"],
                    "recommendations": [],
                },
            }
        )
        result = await node(state)
        rd = result["result_data"]
        assert not any("Found 10 articles" in f for f in rd["findings"])
        assert any("Reuters" in f for f in rd["findings"])
        assert any("Blog authored" in f for f in rd["findings"])

    async def test_extracts_bsi_score(self):
        """ManagerNode extracts BSI score from intelligence agent output."""
        node = ManagerNode()
        state = _base_state(
            node_outputs={
                "valuation_logic": {
                    "findings": ["Brand value estimated at $1.2M"],
                    "recommendations": ["Improve awareness"],
                    "bsi": {
                        "score": 72,
                        "pillars": [
                            {"name": "Financial", "score": 65},
                            {"name": "Behavioral", "score": 78},
                            {"name": "Legal", "score": 70},
                        ],
                        "data_completeness": 0.67,
                    },
                    "valuation": {
                        "brand_value_npv": 1245177.38,
                        "royalty_rate": 0.04,
                    },
                },
            }
        )
        result = await node(state)
        rd = result["result_data"]
        assert rd["score"] == 72
        assert rd["financials"] == 65
        assert rd["awareness"] == 78
        assert rd["sentiment"] == 70
        assert rd["valuation"]["brand_value_npv"] == 1245177.38


# ── Stemmer tests ──


class TestStemmer:
    """Test the simple suffix-stripping stemmer."""

    def test_stem_competitors(self):
        assert _stem("competitors") == "competitor"

    def test_stem_analyzing(self):
        assert _stem("analyzing") == "analyz"

    def test_stem_valuations(self):
        assert _stem("valuations") == "valuation"

    def test_stem_short_word_unchanged(self):
        assert _stem("ai") == "ai"
        assert _stem("the") == "the"

    def test_stem_no_suffix_unchanged(self):
        assert _stem("brand") == "brand"


# ── Stemming-based routing tests ──


class TestStemmingRouting:
    """Test that stemming enables correct routing for inflected words."""

    async def test_competitors_routes_to_competitor_audit(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="analyze our competitors in the market")
        )
        assert result["resolved_manifest_id"] == "competitor-audit"

    async def test_valuations_routes_to_iso_brand_equity(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="run brand valuations for our company")
        )
        assert result["resolved_manifest_id"] == "iso-brand-equity"

    async def test_analyzing_routes_to_brand_analysis(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="analyzing brand positioning deeply")
        )
        assert result["resolved_manifest_id"] == "brand-analysis"


# ── RAG boost tests ──


class TestNeedsRagBoost:
    """Test that needs_rag flag boosts RAG pipelines."""

    async def test_needs_rag_boosts_rag_blog_authoring(self):
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="write a blog about this",
                input_context={"company_id": 42, "needs_rag": True},
            )
        )
        assert result["resolved_manifest_id"] == "rag-blog-authoring"

    async def test_needs_rag_boosts_general_chat(self):
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="hello what is this",
                input_context={"company_id": 42, "needs_rag": True},
            )
        )
        assert result["resolved_manifest_id"] == "general-chat"

    async def test_no_needs_rag_no_boost(self):
        """Without needs_rag, 'write a blog about this' stays blog-authoring."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="write a blog about this",
                input_context={"company_id": 42},
            )
        )
        assert result["resolved_manifest_id"] == "blog-authoring"
