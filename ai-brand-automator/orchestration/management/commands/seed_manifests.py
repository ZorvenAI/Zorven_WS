"""
Management command to seed default pipeline manifests.

Idempotent — skips manifests that already exist (matched
on pipeline_id + version).  Safe to run on every deploy.
"""

from django.core.management.base import BaseCommand

from orchestration.models import PipelineManifest


class Command(BaseCommand):
    help = "Seed default pipeline manifests (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix-edges",
            action="store_true",
            default=False,
            help="Also fix competitor_intel edge typos in existing manifests",
        )

    MANIFESTS = [
        {
            "pipeline_id": "iso-brand-equity",
            "name": "ISO Brand Equity Valuation",
            "description": (
                "ISO 10668-compliant brand equity valuation "
                "using Royalty Relief method. Requires "
                "financial data (10-K) and performs web "
                "research for market benchmarks."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "web_research",
                        "type": "external",
                        "url": "http://discovery-agent-svc:8020/v1/search",
                        "config": {
                            "focus": (
                                "royalty_rates," "market_trends," "brand_rankings"
                            ),
                        },
                    },
                    {
                        "id": "valuation_logic",
                        "type": "external",
                        "url": "http://intelligence-agent-svc:8030/v1/iso-calc",
                        "config": {
                            "method": "royalty_relief",
                            "horizon_years": 5,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "web_research"],
                    ["web_research", "valuation_logic"],
                    ["valuation_logic", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.3,
                },
            },
        },
        {
            "pipeline_id": "brand-analysis",
            "name": "Brand Analysis",
            "description": (
                "Analyze brand positioning, market fit, " "and growth opportunities"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": "http://discovery-agent-svc:8020/v1/search",
                        "config": {
                            "focus": "market_trends,competitors",
                        },
                    },
                    {
                        "id": "brand_strategist",
                        "type": "internal",
                        "handler": "StrategyNode",
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "brand_strategist"],
                    ["brand_strategist", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
        {
            "pipeline_id": "competitor-audit",
            "name": "Competitor Audit",
            "description": (
                "Identify competitors, analyze gaps, "
                "and recommend differentiation strategies"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "competitor_research",
                        "type": "external",
                        "url": "http://discovery-agent-svc:8020/v1/search",
                        "config": {
                            "focus": "competitors,market_share",
                        },
                    },
                    {
                        "id": "gap_analyzer",
                        "type": "external",
                        "url": "http://intelligence-agent-svc:8030/v1/analyze",
                        "config": {
                            "analysis_type": "competitive_gap",
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "competitor_research"],
                    ["competitor_research", "gap_analyzer"],
                    ["gap_analyzer", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.5,
                },
            },
        },
        {
            "pipeline_id": "general-chat",
            "name": "General Chat (RAG)",
            "description": (
                "Conversational AI assistant with knowledge "
                "base retrieval from uploaded documents"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "default_agent",
                        "type": "internal",
                        "handler": "DefaultAgentNode",
                    }
                ],
                "edges": [],
                "global_config": {},
            },
        },
        {
            "pipeline_id": "blog-authoring",
            "name": "Blog Authoring",
            "description": (
                "Research a topic and author a data-backed, "
                "SEO/AEO/GEO-compliant blog post in brand voice"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "web_research",
                        "type": "external",
                        "url": "http://discovery-agent-svc:8020/v1/search",
                        "config": {
                            "focus": "topic_research,statistics,trends",
                        },
                    },
                    {
                        "id": "blog_author",
                        "type": "external",
                        "url": "http://content-agent-svc:8050/v1/execute",
                        "config": {
                            "output_format": "markdown",
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "web_research"],
                    ["web_research", "blog_author"],
                    ["blog_author", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
        {
            "pipeline_id": "social-promotion",
            "name": "Social Media Promotion",
            "description": (
                "Research a topic, author a blog post, and "
                "automatically promote it across social media platforms"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "web_research",
                        "type": "external",
                        "url": "http://discovery-agent-svc:8020/v1/search",
                        "config": {
                            "focus": "topic_research,statistics,trends",
                        },
                    },
                    {
                        "id": "blog_author",
                        "type": "external",
                        "url": "http://content-agent-svc:8050/v1/execute",
                        "config": {
                            "output_format": "markdown",
                        },
                    },
                    {
                        "id": "social_promoter",
                        "type": "external",
                        "url": "http://social-agent-svc:8060/v1/execute",
                        "config": {
                            "platforms": ["linkedin", "twitter"],
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "web_research"],
                    ["web_research", "blog_author"],
                    ["blog_author", "social_promoter"],
                    ["social_promoter", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
        {
            "pipeline_id": "social-post",
            "name": "Social Media Post",
            "description": (
                "Post content directly to connected " "social media platforms"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "social_promoter",
                        "type": "external",
                        "url": "http://social-agent-svc:8060/v1/execute",
                        "config": {
                            "platforms": ["linkedin", "twitter"],
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "social_promoter"],
                    ["social_promoter", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
        {
            "pipeline_id": "rag-blog-social",
            "name": "RAG Blog + Social Promotion",
            "description": (
                "Retrieve and review documents from the Vertex AI "
                "data store, author a blog post from the findings, "
                "and promote it across social media platforms"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "default_agent",
                        "type": "internal",
                        "handler": "DefaultAgentNode",
                    },
                    {
                        "id": "blog_author",
                        "type": "external",
                        "url": "http://content-agent-svc:8050/v1/execute",
                        "config": {
                            "output_format": "markdown",
                        },
                    },
                    {
                        "id": "social_promoter",
                        "type": "external",
                        "url": "http://social-agent-svc:8060/v1/execute",
                        "config": {
                            "platforms": ["linkedin", "twitter"],
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["default_agent", "blog_author"],
                    ["blog_author", "social_promoter"],
                    ["social_promoter", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
        {
            "pipeline_id": "rag-blog-authoring",
            "name": "RAG Blog Authoring",
            "description": (
                "Retrieve and review documents from the Vertex AI "
                "data store and author a blog post from the findings"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "default_agent",
                        "type": "internal",
                        "handler": "DefaultAgentNode",
                    },
                    {
                        "id": "blog_author",
                        "type": "external",
                        "url": "http://content-agent-svc:8050/v1/execute",
                        "config": {
                            "output_format": "markdown",
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["default_agent", "blog_author"],
                    ["blog_author", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
        {
            "pipeline_id": "content-strategy",
            "name": "Content Strategy",
            "description": (
                "Generate content plans, audience analysis, " "and editorial calendars"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "audience_analyzer",
                        "type": "internal",
                        "handler": "AudienceNode",
                    },
                    {
                        "id": "content_planner",
                        "type": "internal",
                        "handler": "PlannerNode",
                    },
                    {
                        "id": "calendar_builder",
                        "type": "internal",
                        "handler": "CalendarNode",
                    },
                ],
                "edges": [
                    ["intent_router", "audience_analyzer"],
                    ["audience_analyzer", "content_planner"],
                    ["content_planner", "calendar_builder"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.7,
                },
            },
        },
        {
            "pipeline_id": "odoo-erp-operations",
            "name": "Odoo ERP Operations",
            "description": (
                "Execute Odoo ERP operations: sales orders, inventory, "
                "accounting, HR, procurement, and other business "
                "processes via a multi-persona AI worker agent"
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "odoo_worker",
                        "type": "external",
                        "url": "http://odoo-worker-agent:8100/v1/execute",
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["odoo_worker", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.3,
                },
            },
        },
        {
            "pipeline_id": "market-research",
            "name": "Market Research & Analysis",
            "description": (
                "Comprehensive market research including market sizing "
                "(TAM/SAM/SOM), competitive landscape analysis, industry "
                "trend tracking, and economic indicator assessment."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": "http://market-research-agent-svc:8021/v1/execute",
                        "config": {
                            "focus": "market_analysis,sizing,"
                            "trends,competitive_landscape",
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.3,
                },
            },
        },
        {
            "pipeline_id": "competitor-intelligence",
            "name": "Competitor Intelligence",
            "description": (
                "Identify and profile competitors, generate SWOT analyses, "
                "positioning gap analysis, and competitive benchmarking reports."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "competitor_intelligence",
                        "type": "external",
                        "url": ("http://competitor-intel-agent-svc:8022/v1/execute"),
                        "config": {
                            "focus": (
                                "competitor_profiling,swot," "benchmarking,positioning"
                            ),
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "competitor_intelligence"],
                    ["competitor_intelligence", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.3,
                },
            },
        },
        {
            "pipeline_id": "market-research-competitor-intel",
            "name": "Market Research + Competitor Intelligence",
            "description": (
                "Comprehensive market research followed by competitor "
                "intelligence analysis. Combines TAM/SAM/SOM sizing with "
                "competitor profiling, SWOT, and benchmarking."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": ("http://market-research-agent-svc:8021/v1/execute"),
                        "config": {
                            "focus": (
                                "market_analysis,sizing," "trends,competitive_landscape"
                            ),
                        },
                    },
                    {
                        "id": "competitor_intelligence",
                        "type": "external",
                        "url": ("http://competitor-intel-agent-svc:8022/v1/execute"),
                        "config": {
                            "focus": (
                                "competitor_profiling,swot," "benchmarking,positioning"
                            ),
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "competitor_intelligence"],
                    ["competitor_intelligence", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.3,
                },
            },
        },
        {
            "pipeline_id": "market-research-report",
            "name": "Market Research Report",
            "description": (
                "Market research followed by a structured research report. "
                "Combines market analysis with content authoring for "
                "publishable reports."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": "http://market-research-agent-svc:8021/v1/execute",
                        "config": {
                            "focus": "market_analysis,sizing,trends",
                        },
                    },
                    {
                        "id": "blog_author",
                        "type": "external",
                        "url": "http://content-agent-svc:8050/v1/execute",
                        "config": {"output_format": "markdown"},
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "blog_author"],
                    ["blog_author", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.5,
                },
            },
        },
        {
            "pipeline_id": "audience-persona",
            "name": "Audience Persona Research",
            "description": (
                "Research and construct data-grounded buyer personas with "
                "demographics, psychographics, behavioral patterns, "
                "motivations, objections, preferred channels, and "
                "buying journey maps."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "audience_persona",
                        "type": "external",
                        "url": ("http://audience-persona-agent-svc:8023/v1/execute"),
                        "config": {
                            "focus": (
                                "buyer_personas,demographics,"
                                "psychographics,buying_journey"
                            ),
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "audience_persona"],
                    ["audience_persona", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.3,
                },
            },
        },
        {
            "pipeline_id": "audience-persona-discovery",
            "name": "Audience Persona Discovery (MRA + CIA + APA)",
            "description": (
                "Full audience discovery pipeline: market research, "
                "competitor intelligence, then audience persona "
                "generation. Combines TAM/SAM/SOM sizing with "
                "competitor profiling and buyer persona construction."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": ("http://market-research-agent-svc:8021/v1/execute"),
                        "config": {
                            "focus": (
                                "market_analysis,sizing," "trends,competitive_landscape"
                            ),
                        },
                    },
                    {
                        "id": "competitor_intelligence",
                        "type": "external",
                        "url": ("http://competitor-intel-agent-svc:8022/v1/execute"),
                        "config": {
                            "focus": (
                                "competitor_profiling,swot," "benchmarking,positioning"
                            ),
                        },
                    },
                    {
                        "id": "audience_persona",
                        "type": "external",
                        "url": ("http://audience-persona-agent-svc:8023/v1/execute"),
                        "config": {
                            "focus": (
                                "buyer_personas,demographics,"
                                "psychographics,buying_journey"
                            ),
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "competitor_intelligence"],
                    ["competitor_intelligence", "audience_persona"],
                    ["audience_persona", "manager"],
                ],
                "global_config": {
                    "model": "gemini-2.0-flash",
                    "temperature": 0.3,
                },
            },
        },
        {
            "pipeline_id": "trend-cultural-insights",
            "name": "Trend & Cultural Insights",
            "description": (
                "Analyze cultural trends, social media patterns, viral content, "
                "and generational shifts for brand relevance. Can run standalone "
                "or with upstream MRA/CIA/APA data for enriched analysis."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "trend_cultural",
                        "type": "external",
                        "url": ("http://trend-cultural-agent-svc:8024/v1/execute"),
                        "config": {
                            "scan_type": "on_demand",
                            "alert_threshold": 75,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "trend_cultural"],
                    ["trend_cultural", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.5,
                },
            },
        },
        {
            "pipeline_id": "voice-of-customer",
            "name": "Voice of Customer Analysis",
            "description": (
                "Analyze customer feedback from reviews, social media, forums, "
                "and Odoo ERP. Produces sentiment analysis, theme clusters, "
                "NPS trends, and strategy recommendations."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "voice_of_customer",
                        "type": "external",
                        "url": "http://voc-agent-svc:8025/v1/execute",
                        "config": {
                            "include_nps": True,
                            "synthesis_type": "comprehensive",
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "voice_of_customer"],
                    ["voice_of_customer", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.5,
                },
            },
        },
        {
            "pipeline_id": "brand-discovery-complete",
            "name": "Brand Discovery & Research (Complete)",
            "description": (
                "Complete brand discovery with all 5 agents: market research, "
                "competitor intelligence, audience personas, trend insights, "
                "and voice of customer analysis."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": "http://market-research-agent-svc:8021/v1/execute",
                        "config": {
                            "focus": (
                                "market_size,segments," "demographics,industry_trends"
                            ),
                        },
                    },
                    {
                        "id": "competitor_intelligence",
                        "type": "external",
                        "url": "http://competitor-intel-agent-svc:8022/v1/execute",
                        "config": {
                            "focus": (
                                "competitor_audiences,"
                                "positioning_gaps,review_sentiment"
                            ),
                        },
                    },
                    {
                        "id": "audience_persona",
                        "type": "external",
                        "url": "http://audience-persona-agent-svc:8023/v1/execute",
                        "config": {"include_crm_data": True},
                    },
                    {
                        "id": "trend_cultural",
                        "type": "external",
                        "url": "http://trend-cultural-agent-svc:8024/v1/execute",
                        "config": {"scan_type": "on_demand"},
                    },
                    {
                        "id": "voice_of_customer",
                        "type": "external",
                        "url": "http://voc-agent-svc:8025/v1/execute",
                        "config": {
                            "include_nps": True,
                            "synthesis_type": "comprehensive",
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "competitor_intelligence"],
                    ["competitor_intelligence", "audience_persona"],
                    ["audience_persona", "trend_cultural"],
                    ["trend_cultural", "voice_of_customer"],
                    ["voice_of_customer", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.5,
                },
            },
        },
        {
            "pipeline_id": "brand-discovery-full",
            "name": "Brand Discovery & Research (Full Workflow)",
            "description": (
                "Complete brand discovery: market research, competitor "
                "intelligence, audience personas, and trend/cultural "
                "insights. Chains all 4 agents in Workflow 1 for "
                "comprehensive brand intelligence."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "market_research",
                        "type": "external",
                        "url": ("http://market-research-agent-svc:8021/v1/execute"),
                        "config": {
                            "focus": (
                                "market_size,segments," "demographics,industry_trends"
                            ),
                        },
                    },
                    {
                        "id": "competitor_intelligence",
                        "type": "external",
                        "url": ("http://competitor-intel-agent-svc:8022/v1/execute"),
                        "config": {
                            "focus": (
                                "competitor_audiences,"
                                "positioning_gaps,review_sentiment"
                            ),
                        },
                    },
                    {
                        "id": "audience_persona",
                        "type": "external",
                        "url": ("http://audience-persona-agent-svc:8023/v1/execute"),
                        "config": {
                            "include_survey_data": True,
                            "include_crm_data": True,
                        },
                    },
                    {
                        "id": "trend_cultural",
                        "type": "external",
                        "url": ("http://trend-cultural-agent-svc:8024/v1/execute"),
                        "config": {
                            "scan_type": "on_demand",
                            "alert_threshold": 75,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "market_research"],
                    ["market_research", "competitor_intelligence"],
                    ["competitor_intelligence", "audience_persona"],
                    ["audience_persona", "trend_cultural"],
                    ["trend_cultural", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.5,
                },
            },
        },
        # ── WF2: Brand Strategy & Positioning (full chain: BPA → BAA → BPV) ──
        {
            "pipeline_id": "brand-strategy-positioning",
            "name": "Brand Strategy & Positioning",
            "description": (
                "Full WF2 brand strategy pipeline: positioning, architecture, "
                "personality & values, naming & tagline, and brand story. "
                "Generates positioning statements, value proposition canvas, "
                "perceptual maps, brand hierarchy tree, Aaker 5D personality "
                "profile, archetype selection, values hierarchy, voice matrix, "
                "brand name candidates with availability checking, taglines, "
                "naming brief, origin stories, mission/vision, elevator pitches, "
                "channel narratives, and story style guide. "
                "Requires completed WF1 Brand Discovery pipeline."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "brand_positioning",
                        "type": "external",
                        "url": (
                            "http://brand-positioning-agent-svc" ":8031/v1/execute"
                        ),
                        "config": {
                            "require_wf1_context": True,
                            "default_candidate_count": 3,
                            "default_perceptual_maps": 3,
                        },
                    },
                    {
                        "id": "brand_architecture",
                        "type": "external",
                        "url": (
                            "http://brand-architecture-agent-svc" ":8032/v1/execute"
                        ),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                        },
                    },
                    {
                        "id": "brand_personality",
                        "type": "external",
                        "url": (
                            "http://brand-personality-agent-svc" ":8033/v1/execute"
                        ),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                        },
                    },
                    {
                        "id": "brand_naming",
                        "type": "external",
                        "url": ("http://brand-naming-agent-svc" ":8034/v1/execute"),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                            "require_bpv_context": True,
                        },
                    },
                    {
                        "id": "brand_story",
                        "type": "external",
                        "url": ("http://brand-story-agent-svc" ":8035/v1/execute"),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                            "require_bpv_context": True,
                            "require_nta_context": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "brand_positioning"],
                    ["brand_positioning", "brand_architecture"],
                    ["brand_architecture", "brand_personality"],
                    ["brand_personality", "brand_naming"],
                    ["brand_naming", "brand_story"],
                    ["brand_story", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.4,
                },
            },
        },
        {
            "pipeline_id": "brand-strategy-architecture",
            "name": "Brand Strategy: Architecture",
            "description": (
                "Design brand architecture using positioning strategy + WF1 "
                "intelligence. Recommends optimal brand structure model "
                "(Branded House, House of Brands, Hybrid, Endorsed, "
                "Sub-Brand), builds brand hierarchy tree for visual "
                "rendering, naming conventions, and portfolio growth path. "
                "Requires completed WF1 Brand Discovery and WF2 Brand "
                "Positioning pipelines."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "brand_architecture",
                        "type": "external",
                        "url": (
                            "http://brand-architecture-agent-svc" ":8032/v1/execute"
                        ),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "brand_architecture"],
                    ["brand_architecture", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.4,
                },
            },
        },
        {
            "pipeline_id": "brand-strategy-personality",
            "name": "Brand Strategy: Personality & Values",
            "description": (
                "Design brand personality using Aaker 5-dimension framework, "
                "Jungian archetype selection, values hierarchy, emotional "
                "attribute mapping, voice matrix, and brand character brief. "
                "Requires completed WF1 Brand Discovery and WF2 Brand "
                "Positioning pipelines. Brand Architecture recommended."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "brand_personality",
                        "type": "external",
                        "url": (
                            "http://brand-personality-agent-svc" ":8033/v1/execute"
                        ),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "brand_personality"],
                    ["brand_personality", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.4,
                },
            },
        },
        {
            "pipeline_id": "brand-strategy-naming",
            "name": "Brand Strategy: Naming & Tagline",
            "description": (
                "Generate brand name candidates with multi-dimensional "
                "scoring, availability checking (domain/social/trademark), "
                "tagline synthesis, and naming brief. Requires completed "
                "WF1 Brand Discovery, WF2 Brand Positioning, and WF2 "
                "Brand Personality pipelines."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "brand_naming",
                        "type": "external",
                        "url": ("http://brand-naming-agent-svc" ":8034/v1/execute"),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                            "require_bpv_context": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "brand_naming"],
                    ["brand_naming", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.4,
                },
            },
        },
        # ── WF2: Brand Story & Narrative (standalone BSA) ──
        {
            "pipeline_id": "brand-strategy-story",
            "name": "Brand Strategy: Story & Narrative",
            "description": (
                "Generate brand narratives: origin story (3 lengths), "
                "mission/vision statements, elevator pitches (15s/30s/60s), "
                "channel narratives (website/social/investor/press), story "
                "style guide, and sub-brand story variations. Requires "
                "completed WF1 Brand Discovery, WF2 Brand Positioning, "
                "WF2 Brand Personality, and WF2 Brand Naming pipelines."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "brand_story",
                        "type": "external",
                        "url": ("http://brand-story-agent-svc" ":8035/v1/execute"),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                            "require_bpv_context": True,
                            "require_nta_context": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "brand_story"],
                    ["brand_story", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.4,
                },
            },
        },
        # ── WF3: Meta Campaign Architecture (standalone CAA) ──
        {
            "pipeline_id": "meta-campaign-architecture",
            "name": "Meta Ads: Campaign Architecture",
            "description": (
                "Design complete Meta Ads campaign structure: campaign "
                "blueprint, funnel-objective mapping, audience targeting "
                "specs, placement/budget strategy (CBO/ABO), A/B test "
                "plan, KPI targets, and creative briefs. First agent in "
                "WF3 Meta Ads workflow. Requires completed WF1 Brand "
                "Discovery (min APA+CIA), WF2 Brand Positioning (min "
                "BPA), and Company model."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "campaign_architecture",
                        "type": "external",
                        "url": (
                            "http://campaign-architecture-agent-svc" ":8041/v1/execute"
                        ),
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                            "require_company_context": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "campaign_architecture"],
                    ["campaign_architecture", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.3,
                },
            },
        },
        # ── WF3: Meta Creative Generation (standalone CGA) ──
        {
            "pipeline_id": "meta-creative-generation",
            "name": "Meta Ads: Creative Generation",
            "description": (
                "Generate complete ad creative packages for Meta Ads: "
                "AI-generated images (Nano Banana 2), funnel-specific "
                "ad copy (hooks, primary text, CTAs), Meta Advertising "
                "Standards compliance, visual-copy assemblies. Second "
                "agent in WF3 Meta Ads workflow. Requires CAA blueprint "
                "+ WF1 + WF2 + Company."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "creative_generation",
                        "type": "external",
                        "url": (
                            "http://creative-generation-agent-svc" ":8042/v1/execute"
                        ),
                        "config": {
                            "require_campaign_blueprint": True,
                            "require_wf1_context": True,
                            "require_wf2_context": True,
                            "require_company_context": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "creative_generation"],
                    ["creative_generation", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.4,
                },
            },
        },
        # ── WF3: Meta Ads Full Pipeline (CAA → CGA → APA) ──
        {
            "pipeline_id": "meta-ads-full",
            "name": "Meta Ads: Full Campaign",
            "description": (
                "Full WF3 Meta Ads pipeline: campaign architecture "
                "(blueprint, funnel mapping, audience targeting, "
                "placement/budget strategy, A/B test plan, creative "
                "briefs) → creative generation (AI-generated ad images, "
                "funnel-specific ad copy with hooks/primary text/CTAs, "
                "Meta Advertising Standards compliance, visual-copy "
                "assemblies) → ad publishing (Meta Ads API campaign "
                "creation, targeting translation, creative upload, "
                "human approval gate, publish + verify). "
                "Chains CAA → CGA → APA. "
                "Requires completed WF1 Brand Discovery and WF2 Brand "
                "Strategy pipelines."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "campaign_architecture",
                        "type": "external",
                        "url": "http://campaign-architecture-agent-svc:8041/v1/execute",
                        "config": {
                            "require_wf1_context": True,
                            "require_bpa_context": True,
                            "require_company_context": True,
                        },
                    },
                    {
                        "id": "creative_generation",
                        "type": "external",
                        "url": "http://creative-generation-agent-svc:8042/v1/execute",
                        "config": {
                            "require_campaign_blueprint": True,
                            "require_wf1_context": True,
                            "require_wf2_context": True,
                            "require_company_context": True,
                        },
                    },
                    {
                        "id": "ad_publishing",
                        "type": "external",
                        "url": "http://ad-publishing-agent-svc:8043/v1/execute",
                        "config": {
                            "require_campaign_blueprint": True,
                            "require_creative_packages": True,
                            "require_meta_credentials": True,
                            "sandbox_mode_default": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "campaign_architecture"],
                    ["campaign_architecture", "creative_generation"],
                    ["creative_generation", "ad_publishing"],
                    ["ad_publishing", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.4,
                },
            },
        },
        # ── WF3: Standalone Ad Publishing ──
        {
            "pipeline_id": "meta-ad-publishing",
            "name": "Meta Ads: Ad Publishing",
            "description": (
                "Standalone ad publishing pipeline: translates approved "
                "creative packages and campaign blueprints into live "
                "Meta Ads API objects. Creates campaigns (PAUSED), "
                "translates persona targeting via Claude, uploads "
                "creatives, assembles ads, generates previews, then "
                "pauses for mandatory human approval. On approval, "
                "publishes and verifies. Requires completed CAA and "
                "CGA pipelines in previous_outputs."
            ),
            "manifest_data": {
                "nodes": [
                    {
                        "id": "intent_router",
                        "type": "internal",
                        "handler": "RouterNode",
                    },
                    {
                        "id": "ad_publishing",
                        "type": "external",
                        "url": "http://ad-publishing-agent-svc:8043/v1/execute",
                        "config": {
                            "require_campaign_blueprint": True,
                            "require_creative_packages": True,
                            "require_meta_credentials": True,
                            "sandbox_mode_default": True,
                        },
                    },
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    },
                ],
                "edges": [
                    ["intent_router", "ad_publishing"],
                    ["ad_publishing", "manager"],
                ],
                "global_config": {
                    "model": "claude-sonnet-4-20250514",
                    "temperature": 0.3,
                },
            },
        },
    ]

    def handle(self, *args, **options):
        self.stdout.write("Seeding default pipeline manifests...")
        for manifest_cfg in self.MANIFESTS:
            obj, created = PipelineManifest.objects.update_or_create(
                pipeline_id=manifest_cfg["pipeline_id"],
                version=1,
                defaults={
                    "name": manifest_cfg["name"],
                    "description": manifest_cfg["description"],
                    "manifest_data": manifest_cfg["manifest_data"],
                    "tenant": None,  # Available to all tenants
                },
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {obj.name}")
        self.stdout.write(self.style.SUCCESS("Pipeline manifest seeding complete."))

        # One-time fixup: patch any manifests with "competitor_intel" edge typo
        # Guarded behind --fix-edges flag to avoid surprise writes on every seed
        if options.get("fix_edges"):
            self._fix_competitor_intel_edges()

    def _fix_competitor_intel_edges(self):
        """Fix 'competitor_intel' → 'competitor_intelligence' in all manifests."""
        import json

        patched = 0
        for manifest in PipelineManifest.objects.all():
            data = manifest.manifest_data
            if not data or "edges" not in data:
                continue
            raw = json.dumps(data)
            if "competitor_intel" not in raw:
                continue
            # Only fix edges where the short form is used but not the full form
            changed = False
            new_edges = []
            for edge in data.get("edges", []):
                src, tgt = edge[0], edge[1]
                if src == "competitor_intel":
                    src = "competitor_intelligence"
                    changed = True
                if tgt == "competitor_intel":
                    tgt = "competitor_intelligence"
                    changed = True
                new_edges.append([src, tgt])
            if changed:
                data["edges"] = new_edges
                manifest.manifest_data = data
                manifest.save(update_fields=["manifest_data", "updated_at"])
                patched += 1
                self.stdout.write(
                    f"  Fixed edges in manifest: {manifest.name} "
                    f"(pipeline_id={manifest.pipeline_id})"
                )
        if patched:
            self.stdout.write(
                self.style.SUCCESS(f"Patched {patched} manifest(s) with edge typo.")
            )
        else:
            self.stdout.write("  No edge typos found.")
