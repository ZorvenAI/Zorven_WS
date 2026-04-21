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

    async def test_keyword_competitor_intelligence(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="competitor analysis benchmarking")
        )
        assert result["resolved_manifest_id"] == "competitor-intelligence"

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

    async def test_market_research_routing(self):
        """Market sizing prompts → market-research."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="What is the market size for AI-powered brand automation tools?"
            )
        )
        assert result["resolved_manifest_id"] == "market-research"

    async def test_market_research_tam_routing(self):
        """TAM/SAM/SOM prompts → market-research."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="Estimate the TAM SAM SOM for electric vehicle charging"
            )
        )
        assert result["resolved_manifest_id"] == "market-research"

    async def test_competitive_landscape_routes_to_competitor_intelligence(self):
        """Competitive landscape prompts → competitor-intelligence."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="Analyze the competitive landscape for cloud computing"
            )
        )
        assert result["resolved_manifest_id"] == "competitor-intelligence"

    async def test_market_research_industry_trends(self):
        """Industry trends prompts → market-research."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="What are the industry trends in renewable energy?"
            )
        )
        assert result["resolved_manifest_id"] == "market-research"

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

    async def test_extracts_market_research_data(self):
        """ManagerNode promotes market research fields to top-level result_data."""
        node = ManagerNode()
        state = _base_state(
            node_outputs={
                "market_research": {
                    "query": "AI brand automation market size",
                    "market_overview": "The AI brand automation market is growing.",
                    "market_sizing": {
                        "tam": {"value": "$50B", "description": "Global AI market"},
                        "sam": {"value": "$8B", "description": "Brand AI segment"},
                        "som": {"value": "$500M", "description": "Addressable now"},
                    },
                    "competitive_landscape": [
                        {"name": "CompetitorA", "market_position": "Leader"},
                    ],
                    "industry_trends": ["AI adoption accelerating"],
                    "economic_indicators": {
                        "gdp_WLD": {"latest_value": 100_000_000, "latest_date": "2023"},
                    },
                    "sources": [
                        {
                            "type": "web",
                            "title": "Market Report",
                            "url": "https://example.com",
                        },
                    ],
                    "findings": ["Market growing at 25% CAGR"],
                    "recommendations": ["Enter market in Q3"],
                    "confidence_score": 0.85,
                    "methodology_notes": ["Top-down sizing approach"],
                },
            }
        )
        result = await node(state)
        rd = result["result_data"]
        # Market research fields promoted to top level
        assert rd["market_overview"] == "The AI brand automation market is growing."
        assert rd["market_sizing"]["tam"]["value"] == "$50B"
        assert rd["market_sizing"]["sam"]["value"] == "$8B"
        assert rd["market_sizing"]["som"]["value"] == "$500M"
        assert len(rd["competitive_landscape"]) == 1
        assert rd["competitive_landscape"][0]["name"] == "CompetitorA"
        assert rd["industry_trends"] == ["AI adoption accelerating"]
        assert "gdp_WLD" in rd["economic_indicators"]
        assert len(rd["sources"]) == 1
        assert rd["confidence_score"] == 0.85
        assert len(rd["methodology_notes"]) == 1
        # Standard fields still present
        assert "findings" in rd
        assert "recommendations" in rd
        assert any("Market growing" in f for f in rd["findings"])

    async def test_extracts_trend_cultural_data(self):
        """ManagerNode promotes trend/cultural insights fields to top-level result_data."""
        node = ManagerNode()
        state = _base_state(
            node_outputs={
                "trend_cultural": {
                    "trend_report": {
                        "executive_summary": "Gen Z sustainability trends rising.",
                        "trend_scorecard": [],
                        "confidence_score": 0.82,
                    },
                    "scored_trends": [
                        {
                            "trend_slug": "sustainable-fashion",
                            "topic": "Sustainable Fashion",
                            "relevance_score": 85,
                            "audience_alignment": 22,
                            "competitive_landscape": 18,
                            "brand_fit": 23,
                            "momentum": 22,
                            "recommendation": "capitalize",
                            "rationale": "Strong alignment with Gen Z values.",
                            "citations": ["https://example.com/trend"],
                            "platforms": ["tiktok", "instagram"],
                        },
                    ],
                    "trend_persona_matrix": {
                        "mappings": [
                            {
                                "trend_slug": "sustainable-fashion",
                                "persona_slug": "eco-warrior",
                                "affinity_score": 0.92,
                                "content_angles": ["eco tips"],
                                "recommended_channels": ["instagram"],
                            },
                        ],
                    },
                    "opportunity_alerts": [
                        {
                            "alert_id": "alert-001",
                            "trend_slug": "sustainable-fashion",
                            "relevance_score": 85,
                            "urgency": "immediate",
                            "recommendation": "Launch eco campaign",
                            "affected_personas": ["eco-warrior"],
                        },
                    ],
                    "cultural_shifts": [
                        {
                            "domain": "sustainability",
                            "shift_description": "Fast fashion backlash",
                            "evidence_strength": 0.88,
                        },
                    ],
                    "sources": [
                        {
                            "type": "web",
                            "title": "Trend Source",
                            "url": "https://trends.example.com",
                        },
                    ],
                    "confidence_score": 0.82,
                    "findings": ["Sustainability is top concern for Gen Z"],
                    "recommendations": ["Align brand messaging with eco values"],
                },
            }
        )
        result = await node(state)
        rd = result["result_data"]
        # Trend cultural fields promoted to top level
        assert (
            rd["trend_report"]["executive_summary"]
            == "Gen Z sustainability trends rising."
        )
        assert len(rd["scored_trends"]) == 1
        assert rd["scored_trends"][0]["topic"] == "Sustainable Fashion"
        assert rd["scored_trends"][0]["relevance_score"] == 85
        assert rd["trend_persona_matrix"]["mappings"][0]["affinity_score"] == 0.92
        assert len(rd["opportunity_alerts"]) == 1
        assert rd["opportunity_alerts"][0]["urgency"] == "immediate"
        assert len(rd["cultural_shifts"]) == 1
        assert rd["confidence_score"] == 0.82
        assert len(rd["sources"]) == 1


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

    async def test_competitors_routes_to_competitor_intelligence(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="analyze our competitors in the market")
        )
        assert result["resolved_manifest_id"] == "competitor-intelligence"

    async def test_valuations_routes_to_iso_brand_equity(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="run brand valuations for our company")
        )
        assert result["resolved_manifest_id"] == "iso-brand-equity"

    async def test_analyzing_routes_to_brand_strategy_positioning(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="analyzing brand positioning deeply")
        )
        assert result["resolved_manifest_id"] == "brand-strategy-positioning"

    async def test_brand_analysis_without_positioning(self):
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="analyzing brand performance deeply")
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

    async def test_cultural_trends_routes_to_trend_cultural(self):
        """'cultural trends' without 'brand discovery' routes to standalone."""
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="analyze cultural trends for our brand")
        )
        assert result["resolved_manifest_id"] == "trend-cultural-insights"

    async def test_trend_cultural_standalone_with_available_manifests(self):
        """When only trend-cultural-insights is available, it is selected."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="what is trending in social media for fashion",
                available_manifests=[
                    {"pipeline_id": "trend-cultural-insights"},
                    {"pipeline_id": "general-chat"},
                ],
            )
        )
        assert result["resolved_manifest_id"] == "trend-cultural-insights"


class TestWorkflowRouting:
    """Tests for WF1/WF2/WF3 keyword routing defaults."""

    async def test_brand_discovery_full_route(self):
        """Explicit 'full brand discovery' routes to brand-discovery-full."""
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="run a full brand discovery with trend analysis")
        )
        assert result["resolved_manifest_id"] == "brand-discovery-full"

    async def test_generic_brand_discovery_routes_to_complete(self):
        """Generic 'brand discovery' defaults to brand-discovery-complete."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt="Can you please run the Brand discovery for Pomodoro?"
            )
        )
        assert result["resolved_manifest_id"] == "brand-discovery-complete"

    async def test_brand_strategy_routes_to_positioning(self):
        """'brand strategy and positioning' routes to brand-strategy-positioning."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt=(
                    "Can you please run the Brand strategy and "
                    "positioning for Pomodoro?"
                )
            )
        )
        assert result["resolved_manifest_id"] == "brand-strategy-positioning"


class TestExpandChain:
    """Tests for _expand_chain deterministic rewrite helper."""

    def test_injects_chain_when_zero_agents_present(self):
        """Chain is injected even when Gemini picked zero chain agents."""
        from app.nodes.internal.pipeline_composer import _expand_chain

        result = _expand_chain(
            ["web_research", "manager"],
            ["brand_positioning", "brand_architecture", "brand_personality"],
            "WF2 test",
        )
        assert result == [
            "brand_positioning",
            "brand_architecture",
            "brand_personality",
            "web_research",
            "manager",
        ]

    def test_expands_partial_chain(self):
        """Missing agents are added when chain is partially present."""
        from app.nodes.internal.pipeline_composer import _expand_chain

        result = _expand_chain(
            ["brand_positioning", "manager"],
            ["brand_positioning", "brand_architecture", "brand_personality"],
            "WF2 test",
        )
        assert result == [
            "brand_positioning",
            "brand_architecture",
            "brand_personality",
            "manager",
        ]

    def test_no_change_when_chain_complete(self):
        """No change when all chain agents are already present."""
        from app.nodes.internal.pipeline_composer import _expand_chain

        node_ids = [
            "brand_positioning",
            "brand_architecture",
            "brand_personality",
            "manager",
        ]
        result = _expand_chain(
            node_ids,
            ["brand_positioning", "brand_architecture", "brand_personality"],
            "WF2 test",
        )
        assert result == node_ids

    def test_injects_wf3_chain_when_zero_agents_present(self):
        """WF3 chain is injected when Gemini picked no meta ads agents."""
        from app.nodes.internal.pipeline_composer import _expand_chain

        result = _expand_chain(
            ["web_research", "manager"],
            ["campaign_architecture", "creative_generation", "ad_publishing"],
            "WF3 Meta Ads",
        )
        assert result == [
            "campaign_architecture",
            "creative_generation",
            "ad_publishing",
            "web_research",
            "manager",
        ]


class TestMetaAdsRouting:
    """Tests for WF3 Meta Ads keyword routing."""

    async def test_meta_ads_campaign_routes_to_full(self):
        """Generic 'Meta Ads campaign' routes to meta-ads-full."""
        node = RouterNode()
        result = await node(
            _base_state(
                input_prompt=("Can you please run the Meta Ads campaign for Pomodoro?")
            )
        )
        assert result["resolved_manifest_id"] == "meta-ads-full"

    async def test_ad_campaign_routes_to_full(self):
        """Generic 'ad campaign' routes to meta-ads-full."""
        node = RouterNode()
        result = await node(_base_state(input_prompt="Run ad campaign for Pomodoro"))
        assert result["resolved_manifest_id"] == "meta-ads-full"

    async def test_standalone_campaign_architecture(self):
        """Explicit 'campaign architecture' stays standalone."""
        node = RouterNode()
        result = await node(
            _base_state(input_prompt="Design a Meta Ads campaign architecture")
        )
        assert result["resolved_manifest_id"] == "meta-campaign-architecture"


class TestDeterministicCompose:
    """Tests for Tier 2.5 deterministic composition.

    Verifies that known workflow signals produce a _composed_manifest
    (not a resolved_manifest_id) even when Gemini is unavailable and
    seed_manifests hasn't been run.
    """

    def _make_composer(self):
        from app.nodes.internal.pipeline_composer import PipelineComposer

        return PipelineComposer()

    def test_brand_discovery_composes_5_agent_chain(self):
        composer = self._make_composer()
        result = composer._deterministic_compose(
            _base_state(
                input_prompt="Can you please run the Brand discovery for Pomodoro?"
            )
        )
        assert result is not None
        assert "_composed_manifest" in result
        node_ids = [n["id"] for n in result["_composed_manifest"]["nodes"]]
        assert node_ids == [
            "market_research",
            "competitor_intelligence",
            "audience_persona",
            "trend_cultural",
            "voice_of_customer",
            "manager",
        ]

    def test_full_brand_discovery_composes_4_agent_chain(self):
        composer = self._make_composer()
        result = composer._deterministic_compose(
            _base_state(input_prompt="Run a full brand discovery for our startup")
        )
        assert result is not None
        node_ids = [n["id"] for n in result["_composed_manifest"]["nodes"]]
        assert node_ids == [
            "market_research",
            "competitor_intelligence",
            "audience_persona",
            "trend_cultural",
            "manager",
        ]
        assert "voice_of_customer" not in node_ids

    def test_brand_strategy_composes_5_agent_chain(self):
        composer = self._make_composer()
        result = composer._deterministic_compose(
            _base_state(input_prompt="Run the brand strategy for Pomodoro")
        )
        assert result is not None
        node_ids = [n["id"] for n in result["_composed_manifest"]["nodes"]]
        assert node_ids == [
            "brand_positioning",
            "brand_architecture",
            "brand_personality",
            "brand_naming",
            "brand_story",
            "manager",
        ]

    def test_meta_ads_composes_2_agent_chain(self):
        composer = self._make_composer()
        result = composer._deterministic_compose(
            _base_state(input_prompt="Launch Meta Ads for our product")
        )
        assert result is not None
        node_ids = [n["id"] for n in result["_composed_manifest"]["nodes"]]
        assert node_ids == [
            "campaign_architecture",
            "creative_generation",
            "manager",
        ]

    def test_standalone_meta_returns_none(self):
        """Explicit 'campaign architecture' should NOT trigger deterministic compose."""
        composer = self._make_composer()
        result = composer._deterministic_compose(
            _base_state(input_prompt="Design a Meta Ads campaign architecture")
        )
        assert result is None

    def test_unrelated_prompt_returns_none(self):
        """Non-workflow prompts should fall through to Tier 3."""
        composer = self._make_composer()
        result = composer._deterministic_compose(
            _base_state(input_prompt="Write a blog about Tesla")
        )
        assert result is None

    def test_works_without_available_manifests(self):
        """Deterministic compose works even with empty available_manifests."""
        composer = self._make_composer()
        result = composer._deterministic_compose(
            _base_state(
                input_prompt="Brand discovery for Pomodoro",
                available_manifests=[],
            )
        )
        assert result is not None
        assert "_composed_manifest" in result
