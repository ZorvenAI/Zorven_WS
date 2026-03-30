"""
PipelineComposer — Dynamic, catalog-driven pipeline composition.

Replaces RouterNode for auto-detect mode. Uses a 3-tier routing chain:

  Tier 1: Enhanced Gemini dynamic composition (context-enriched + retry)
  Tier 2: Gemini manifest classification (lightweight LLM picks 1 of 9)
  Tier 3: Improved keyword matching (stemming, weights, neutral default)

Falls back through the tiers on failure. Adding a new agent requires
only one dict entry in NODE_CATALOG.
"""

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.nodes.internal.router_node import keyword_match
from app.state.schema import AgentState
from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)

# ── Node Catalog — single source of truth for available agents ──

NODE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "default_agent",
        "type": "internal",
        "handler": "DefaultAgentNode",
        "description": (
            "RAG specialist: retrieves and analyzes documents from the "
            "user's Vertex AI data store / knowledge base. Use when the "
            "prompt references uploaded documents, the RAG store, vertex "
            "store, knowledge base, or asks to review/summarize a "
            "specific document."
        ),
        "output_key": "default_agent",
    },
    {
        "id": "web_research",
        "type": "external",
        "url": f"{settings.DISCOVERY_AGENT_URL}/v1/search",
        "description": (
            "Web research: searches the internet via Tavily for current "
            "data, statistics, trends, competitor info. Use when the "
            "prompt needs fresh web data, market research, or doesn't "
            "reference uploaded documents."
        ),
        "output_key": "web_research",
        "config": {"focus": "topic_research,statistics,trends"},
    },
    {
        "id": "blog_author",
        "type": "external",
        "url": f"{settings.CONTENT_AGENT_URL}/v1/execute",
        "description": (
            "Blog author: writes SEO-optimized blog posts in markdown. "
            "Needs research input from either web_research or "
            "default_agent. Use when the prompt asks to write, author, "
            "or create a blog post or article."
        ),
        "output_key": "blog_author",
        "config": {"output_format": "markdown"},
    },
    {
        "id": "social_promoter",
        "type": "external",
        "url": f"{settings.SOCIAL_AGENT_URL}/v1/execute",
        "description": (
            "Social media promoter: adapts content for social platforms "
            "and publishes or schedules posts. Use when the prompt "
            "mentions LinkedIn, Twitter, Facebook, Instagram, social "
            "media, posting, sharing, scheduling, or promoting."
        ),
        "output_key": "social_promoter",
        "config": {"platforms": ["linkedin", "twitter"]},
    },
    {
        "id": "valuation_logic",
        "type": "external",
        "url": f"{settings.INTELLIGENCE_AGENT_URL}/v1/iso-calc",
        "description": (
            "ISO 10668 brand valuation using Royalty Relief NPV. Use "
            "when the prompt asks about brand valuation, brand equity, "
            "ISO, royalty, or NPV."
        ),
        "output_key": "valuation_logic",
        "config": {"method": "royalty_relief", "horizon_years": 5},
    },
    {
        "id": "gap_analyzer",
        "type": "external",
        "url": f"{settings.INTELLIGENCE_AGENT_URL}/v1/analyze",
        "description": (
            "Brand gap analysis using intelligence agent. Use when the "
            "prompt asks for brand audit, brand gaps, or brand "
            "performance comparison against ISO benchmarks."
        ),
        "output_key": "gap_analyzer",
        "config": {"analysis_type": "competitive_gap"},
    },
    {
        "id": "rag_uploader",
        "type": "external",
        "url": f"{settings.RAG_UPLOADER_AGENT_URL}/v1/execute",
        "description": (
            "RAG archivist: persists documents and files to the tenant's "
            "long-term Vertex AI knowledge base. Use when the user wants "
            "to save, archive, upload, store, or persist files to their "
            "knowledge base, RAG store, or document library. Also use "
            "when the user says 'remember this' or 'keep this for later'."
        ),
        "output_key": "rag_uploader",
        "config": {},
    },
    {
        "id": "odoo_worker",
        "type": "external",
        "url": f"{settings.ODOO_WORKER_AGENT_URL}/v1/execute",
        "description": (
            "Odoo ERP worker agent: assumes a business persona "
            "(sales, accounting, HR, marketing, etc.) and executes "
            "multi-step Odoo operations via MCP tools. Use for "
            "general or ambiguous Odoo tasks that don't clearly "
            "fit a single domain."
        ),
        "output_key": "odoo_worker",
        "config": {},
    },
    # ── Persona-specific Odoo workers ──
    # Each targets the same service URL but with a persona_hint
    # so the worker agent skips auto-resolution and uses the
    # correct persona directly. Use these for multi-domain Odoo
    # tasks that require outputs to flow between personas.
    {
        "id": "odoo_sales_crm",
        "type": "external",
        "url": f"{settings.ODOO_WORKER_AGENT_URL}/v1/execute",
        "description": (
            "Odoo Sales/CRM specialist: handles sales orders, "
            "quotations, CRM leads, opportunities, customers, "
            "contacts, and product lookups. Use when the task "
            "involves finding customer or product data in Odoo."
        ),
        "output_key": "odoo_sales_crm",
        "config": {"persona_hint": "sales_manager"},
    },
    {
        "id": "odoo_finance",
        "type": "external",
        "url": f"{settings.ODOO_WORKER_AGENT_URL}/v1/execute",
        "description": (
            "Odoo Finance specialist: handles invoices, payments, "
            "accounting entries, financial reports, and bank "
            "reconciliation. Use when the task involves billing, "
            "invoicing, or financial operations."
        ),
        "output_key": "odoo_finance",
        "config": {"persona_hint": "accountant"},
    },
    {
        "id": "odoo_inventory",
        "type": "external",
        "url": f"{settings.ODOO_WORKER_AGENT_URL}/v1/execute",
        "description": (
            "Odoo Inventory specialist: handles stock levels, "
            "warehouse transfers, receipts, deliveries, and "
            "reordering rules. Use when the task involves "
            "inventory checks or warehouse operations."
        ),
        "output_key": "odoo_inventory",
        "config": {"persona_hint": "warehouse_manager"},
    },
    {
        "id": "odoo_hr",
        "type": "external",
        "url": f"{settings.ODOO_WORKER_AGENT_URL}/v1/execute",
        "description": (
            "Odoo HR specialist: handles employees, leave "
            "requests, payroll, recruitment, and attendance. "
            "Use when the task involves HR or workforce "
            "management."
        ),
        "output_key": "odoo_hr",
        "config": {"persona_hint": "hr_manager"},
    },
    {
        "id": "odoo_marketing",
        "type": "external",
        "url": f"{settings.ODOO_WORKER_AGENT_URL}/v1/execute",
        "description": (
            "Odoo Marketing specialist: handles email campaigns, "
            "mass mailings, newsletters, marketing automation, "
            "and contact lists. Use when the task involves email "
            "marketing, campaigns, or mass communication in Odoo."
        ),
        "output_key": "odoo_marketing",
        "config": {"persona_hint": "marketing_manager"},
    },
    {
        "id": "odoo_manufacturing",
        "type": "external",
        "url": f"{settings.ODOO_WORKER_AGENT_URL}/v1/execute",
        "description": (
            "Odoo Manufacturing specialist: handles production "
            "orders, bills of materials (BOM), work orders, and "
            "manufacturing planning. Use when the task involves "
            "production or manufacturing operations."
        ),
        "output_key": "odoo_manufacturing",
        "config": {"persona_hint": "manufacturing_supervisor"},
    },
    {
        "id": "market_research",
        "type": "external",
        "url": f"{settings.MARKET_RESEARCH_AGENT_URL}/v1/execute",
        "description": (
            "Market research specialist: analyzes market size (TAM/SAM/SOM), "
            "industry trends, competitive landscape, and economic indicators. "
            "Uses web search, World Bank data, and news APIs. Use when the "
            "prompt asks about market sizing, market analysis, industry trends, "
            "growth potential, addressable market, or market opportunity."
        ),
        "output_key": "market_research",
        "config": {"focus": "market_analysis,sizing,trends,competitive_landscape"},
    },
    {
        "id": "competitor_intelligence",
        "type": "external",
        "url": f"{settings.COMPETITOR_INTEL_AGENT_URL}/v1/execute",
        "description": (
            "Competitive intelligence specialist: identifies and profiles "
            "competitors, generates SWOT analyses, positioning gap analysis, "
            "and competitive benchmarking reports. Uses web search, website "
            "scraping, review aggregation, and Claude for analysis. Use when "
            "the prompt asks about competitors, competitive landscape, SWOT, "
            "market positioning, benchmarking, or competitive strategy."
        ),
        "output_key": "competitor_intelligence",
        "config": {
            "focus": "competitor_profiling,swot,positioning,benchmarking",
        },
    },
    {
        "id": "audience_persona",
        "type": "external",
        "url": f"{settings.AUDIENCE_PERSONA_AGENT_URL}/v1/execute",
        "description": (
            "Audience persona specialist: researches and constructs data-grounded "
            "buyer personas with demographics, psychographics, behavioral patterns, "
            "motivations, objections, preferred channels, and buying journey maps. "
            "Integrates Odoo CRM customer data and survey responses. Use when the "
            "prompt asks about target audience, buyer personas, customer segments, "
            "demographics, psychographics, customer profiles, buying journey, or "
            "audience research."
        ),
        "output_key": "audience_persona",
        "config": {
            "focus": "buyer_personas,demographics,psychographics,buying_journey",
        },
    },
    {
        "id": "trend_cultural",
        "type": "external",
        "url": f"{settings.TREND_CULTURAL_AGENT_URL}/v1/execute",
        "description": (
            "Trend & cultural insights specialist: monitors cultural shifts, "
            "social media trends, viral content patterns, emerging slang, and "
            "generational preferences for brand relevance. Produces trend reports "
            "with cultural relevance scores (0-100), trend-to-persona mappings, "
            "and opportunity alerts. Best used after market research, competitor "
            "intelligence, and audience persona analysis for enriched context. "
            "Use when the prompt asks about cultural trends, what's trending, "
            "viral content, generational preferences, or brand relevance."
        ),
        "output_key": "trend_cultural",
        "config": {"scan_type": "on_demand", "alert_threshold": 75},
    },
    {
        "id": "voice_of_customer",
        "type": "external",
        "url": f"{settings.VOC_AGENT_URL}/v1/execute",
        "description": (
            "Voice of Customer specialist: aggregates and analyzes customer "
            "feedback from reviews, social media, forums, and Odoo ERP "
            "(helpdesk tickets, surveys, CRM chatter). Produces sentiment "
            "analysis, theme clusters, NPS trends, pain point rankings, "
            "and a VoC-to-strategy bridge document. Best used as the final "
            "agent after market research, competitor intelligence, audience "
            "personas, and trend insights for the most complete analysis. "
            "Use when the prompt asks about customer feedback, customer "
            "sentiment, NPS, net promoter score, customer complaints, "
            "support ticket analysis, pain points, or voice of customer."
        ),
        "output_key": "voice_of_customer",
        "config": {"include_nps": True, "synthesis_type": "comprehensive"},
    },
    {
        "id": "brand_positioning",
        "type": "external",
        "url": f"{settings.BRAND_POSITIONING_AGENT_URL}/v1/execute",
        "description": (
            "Brand positioning strategist: generates framework-agnostic "
            "positioning statements, value proposition canvas, perceptual "
            "maps, and differentiation framework (POPs/PODs/RTBs). Requires "
            "WF1 Brand Discovery data as input context. Best used after a "
            "completed brand discovery pipeline. Use when the prompt asks "
            "about brand positioning, positioning strategy, unique value "
            "proposition, UVP, differentiation, competitive positioning, "
            "perceptual mapping, or value proposition canvas."
        ),
        "output_key": "brand_positioning",
        "config": {"candidate_count": 3, "perceptual_maps": 3},
    },
    {
        "id": "brand_architecture",
        "type": "external",
        "url": f"{settings.BRAND_ARCHITECTURE_AGENT_URL}/v1/execute",
        "description": (
            "Brand architecture designer: recommends optimal brand structure "
            "(Branded House, House of Brands, Hybrid/Endorsed, Sub-Brand), "
            "builds brand hierarchy tree, naming conventions, and portfolio "
            "growth path. Requires WF1 Brand Discovery AND BPA Brand "
            "Positioning data as input context. Best used after completed "
            "brand discovery and brand positioning pipelines. Use when the "
            "prompt asks about brand architecture, brand hierarchy, sub-brands, "
            "brand portfolio structure, branded house, house of brands, naming "
            "hierarchy, or brand structure."
        ),
        "output_key": "brand_architecture",
        "config": {"require_wf1_context": True, "require_bpa_context": True},
    },
    {
        "id": "brand_personality",
        "type": "external",
        "url": f"{settings.BRAND_PERSONALITY_AGENT_URL}/v1/execute",
        "description": (
            "Brand personality & values designer: Aaker 5-dimension "
            "personality profile, Jungian archetypes (primary + secondary), "
            "values hierarchy (core/supporting/aspirational), emotional "
            "attribute map, voice matrix, and character brief. Requires "
            "WF1 Brand Discovery AND BPA Brand Positioning data. BAA Brand "
            "Architecture recommended but not required. Use when the prompt "
            "asks about brand personality, brand character, brand values, "
            "brand voice, brand tone, archetypes, personality traits, "
            "values hierarchy, or voice matrix."
        ),
        "output_key": "brand_personality",
        "config": {"require_wf1_context": True, "require_bpa_context": True},
    },
    {
        "id": "brand_naming",
        "type": "external",
        "url": f"{settings.BRAND_NAMING_AGENT_URL}/v1/execute",
        "description": (
            "Brand naming & tagline agent: generates 7-15 name candidates "
            "with multi-dimensional scoring (linguistic, memorability, "
            "availability, strategy alignment), checks domain/social/trademark "
            "availability, synthesizes taglines for shortlisted names, and "
            "produces a naming brief. Requires WF1 + BPA + BPV. Use when the "
            "prompt asks about brand naming, taglines, slogans, name "
            "candidates, or naming strategy."
        ),
        "output_key": "brand_naming",
        "config": {
            "require_wf1_context": True,
            "require_bpa_context": True,
            "require_bpv_context": True,
        },
    },
    {
        "id": "brand_story",
        "type": "external",
        "url": f"{settings.BRAND_STORY_AGENT_URL}/v1/execute",
        "description": (
            "Brand story & narrative agent: crafts origin stories (3 lengths), "
            "mission/vision statements, elevator pitches (15s/30s/60s), "
            "channel narratives (website/social/investor/press), story style "
            "guide, and sub-brand story variations. Capstone WF2 agent that "
            "synthesizes all prior strategy work. Requires WF1 + BPA + BPV + NTA."
        ),
        "output_key": "brand_story",
        "config": {
            "require_wf1_context": True,
            "require_bpa_context": True,
            "require_bpv_context": True,
            "require_nta_context": True,
        },
    },
    # ──────────────────────────────────────────────────────────
    # TO ADD A NEW AGENT: Simply append an entry here.
    # The PipelineComposer will automatically pick it up.
    # ──────────────────────────────────────────────────────────
]

# Fast lookup by node id
NODE_CATALOG_MAP: dict[str, dict[str, Any]] = {n["id"]: n for n in NODE_CATALOG}

# ── Available pipeline manifests for Tier 2 classification ──

_PIPELINE_DESCRIPTIONS: list[dict[str, str]] = [
    {
        "id": "brand-analysis",
        "description": "Full brand analysis: positioning, market, audience insights",
    },
    {
        "id": "blog-authoring",
        "description": "Write SEO-optimized blog posts using web research",
    },
    {
        "id": "social-promotion",
        "description": "Create and publish social media posts (LinkedIn, Twitter, etc.)",
    },
    {
        "id": "iso-brand-equity",
        "description": "ISO 10668 brand valuation using Royalty Relief NPV method",
    },
    {
        "id": "competitor-audit",
        "description": "Brand gap audit: brand performance analysis against ISO benchmarks",
    },
    {
        "id": "content-strategy",
        "description": "Editorial calendar and content strategy planning",
    },
    {
        "id": "general-chat",
        "description": "General Q&A, document analysis, and RAG-based queries",
    },
    {
        "id": "rag-blog-social",
        "description": ("Blog + social posting using RAG documents (not web research)"),
    },
    {
        "id": "rag-blog-authoring",
        "description": "Blog authoring using RAG documents (not web research)",
    },
    {
        "id": "odoo-erp-operations",
        "description": (
            "Odoo ERP operations: sales orders, inventory, accounting, "
            "HR, procurement, email campaigns, mass mailing, email "
            "marketing, manufacturing, and other business processes "
            "via Odoo"
        ),
    },
    {
        "id": "market-research",
        "description": (
            "Market research and analysis: market sizing (TAM/SAM/SOM), "
            "competitive landscape, industry trends, economic indicators"
        ),
    },
    {
        "id": "competitor-intelligence",
        "description": (
            "Competitive intelligence: competitor profiling, SWOT analysis, "
            "positioning gap analysis, competitive benchmarking reports"
        ),
    },
    {
        "id": "market-research-competitor-intel",
        "description": (
            "Combined market research and competitive intelligence: "
            "market sizing followed by deep competitor analysis"
        ),
    },
    {
        "id": "audience-persona",
        "description": (
            "Audience persona research: buyer personas with demographics, "
            "psychographics, buying journeys, and customer segmentation"
        ),
    },
    {
        "id": "audience-persona-discovery",
        "description": (
            "Full audience discovery pipeline: market research, competitor "
            "intelligence, then audience persona generation with CRM data"
        ),
    },
    {
        "id": "trend-cultural-insights",
        "description": (
            "Trend & cultural insights: cultural shifts, social media trends, "
            "viral content patterns, generational preferences, emerging slang, "
            "and brand cultural relevance scoring with opportunity alerts"
        ),
    },
    {
        "id": "voice-of-customer",
        "description": (
            "Voice of customer analysis: customer feedback aggregation, "
            "sentiment analysis, theme clustering, NPS trends, and "
            "VoC-to-strategy bridge from reviews, social, forums, and Odoo"
        ),
    },
    {
        "id": "brand-discovery-full",
        "description": (
            "Complete brand discovery workflow: market research, competitor "
            "intelligence, audience personas, and trend/cultural insights. "
            "Full 4-agent chain for comprehensive brand intelligence"
        ),
    },
    {
        "id": "brand-discovery-complete",
        "description": (
            "Complete brand discovery workflow with all 5 agents: market "
            "research, competitor intelligence, audience personas, trend "
            "insights, AND voice of customer analysis. The most comprehensive "
            "brand intelligence pipeline available"
        ),
    },
    {
        "id": "brand-strategy-positioning",
        "description": (
            "Brand strategy and positioning: generates positioning statements, "
            "value proposition canvas, perceptual maps, and differentiation "
            "framework. Requires completed WF1 Brand Discovery data"
        ),
    },
    {
        "id": "brand-strategy-architecture",
        "description": (
            "Brand architecture design: recommends optimal brand structure "
            "(branded house, house of brands, endorsed, hybrid), builds "
            "brand hierarchy tree, naming conventions, and portfolio growth "
            "path. Requires completed WF1 Brand Discovery and WF2 Brand "
            "Positioning data"
        ),
    },
    {
        "id": "brand-strategy-story",
        "description": (
            "Brand story & narrative: origin story (3 lengths), mission/vision, "
            "elevator pitches (15s/30s/60s), channel narratives, story style "
            "guide. Capstone WF2 agent. Requires WF1 + BPA + BPV + NTA"
        ),
    },
]

# ── Few-shot examples for Tier 1 ──

_FEW_SHOT_EXAMPLES = """
Examples of prompt → pipeline compositions:
- "Write a blog about Tesla" → [web_research, blog_author, manager]
- "Post about our brand on LinkedIn" → [web_research, blog_author, social_promoter, manager]
- "Calculate brand equity for Nike" → [web_research, valuation_logic, manager]
- "Analyze our competitors in the SaaS market" → [competitor_intelligence, manager]
- "Summarize the document I uploaded" → [default_agent, manager]
- "Write a blog from the uploaded brand study and share on LinkedIn" → [default_agent, blog_author, social_promoter, manager]
- "Create a sales order for 100 units of Product X in Odoo" → [odoo_sales_crm, manager]
- "Check inventory levels and reorder low-stock items in Odoo" → [odoo_inventory, manager]
- "Launch an email campaign for our new product" → node_ids: [odoo_sales_crm, odoo_marketing, manager], sub_tasks: '{"odoo_sales_crm": "Find the product details and customer contact list", "odoo_marketing": "Create and send the email campaign using the product and customer data"}'
- "Send a mass mailing to all customers about the sale" → node_ids: [odoo_sales_crm, odoo_marketing, manager], sub_tasks: '{"odoo_sales_crm": "Retrieve the customer contact list", "odoo_marketing": "Create and send the mass mailing to the customers"}'
- "Create a sales order and generate the invoice" → node_ids: [odoo_sales_crm, odoo_finance, manager], sub_tasks: '{"odoo_sales_crm": "Create the sales order", "odoo_finance": "Generate the invoice for the sales order"}'
- "Create a marketing campaign in Odoo" → [odoo_marketing, manager]
- "Approve leave request for John" → [odoo_hr, manager]
- "Check production order status" → [odoo_manufacturing, manager]
- "Check inventory levels and sales pipeline status" → node_ids: [odoo_sales_crm, odoo_inventory, manager], dependencies: '{"odoo_sales_crm": "", "odoo_inventory": "", "manager": "odoo_sales_crm,odoo_inventory"}'
- "Get employee list and check stock levels" → node_ids: [odoo_hr, odoo_inventory, manager], dependencies: '{"odoo_hr": "", "odoo_inventory": "", "manager": "odoo_hr,odoo_inventory"}'
- "What is the market size for AI-powered brand tools?" → [market_research, manager]
- "Analyze the SaaS market opportunity and write a report" → [market_research, blog_author, manager]
- "Research the competitive landscape for EV charging" → [market_research, manager]
- "What are the industry trends in renewable energy and how does our brand fit?" → [web_research, market_research, manager]
- "Who are our main competitors in the SaaS CRM space?" → [competitor_intelligence, manager]
- "Run a SWOT analysis on our top competitors" → [competitor_intelligence, manager]
- "Analyze the competitive landscape and benchmark our brand" → [market_research, competitor_intelligence, manager]
- "Research the market and profile our competitors in EV charging" → [market_research, competitor_intelligence, manager]
- "What positioning gaps exist in the project management tool market?" → [competitor_intelligence, manager]
- "Who is our target audience for the new SaaS product?" → [audience_persona, manager]
- "Create buyer personas for our EV charging brand" → [audience_persona, manager]
- "Research audience demographics and psychographics for organic food" → [audience_persona, manager]
- "Map the buying journey for enterprise software buyers" → [audience_persona, manager]
- "Research the market, competitors, and build buyer personas for fintech" → [market_research, competitor_intelligence, audience_persona, manager]
- "Analyze our audience segments and their competitive preferences" → [competitor_intelligence, audience_persona, manager]
- "What cultural trends should our brand capitalize on?" → [trend_cultural, manager]
- "Analyze social media trends and viral content patterns for skincare" → [trend_cultural, manager]
- "What's trending on TikTok and Instagram for our industry?" → [trend_cultural, manager]
- "Track generational preferences and emerging slang for our Gen Z audience" → [trend_cultural, manager]
- "Brand discovery for AI brand building application in Pittsburgh PA" → [market_research, competitor_intelligence, audience_persona, trend_cultural, manager]
- "Brand discovery for a SaaS startup in healthcare" → [market_research, competitor_intelligence, audience_persona, trend_cultural, manager]
- "Run a full brand discovery with market research, competitors, personas, and cultural trends" → [market_research, competitor_intelligence, audience_persona, trend_cultural, manager]
- "Complete brand analysis including trend insights for a DTC fashion brand" → [market_research, competitor_intelligence, audience_persona, trend_cultural, manager]
- "Do a brand discovery for our new product line" → [market_research, competitor_intelligence, audience_persona, trend_cultural, manager]
- "Analyze the market, competitors, and cultural trends for renewable energy" → [market_research, competitor_intelligence, trend_cultural, manager]
- "Analyze customer feedback for our brand" → [voice_of_customer, manager]
- "What are our customers saying about us?" → [voice_of_customer, manager]
- "Run NPS analysis and customer sentiment" → [voice_of_customer, manager]
- "Analyze customer complaints and support tickets" → [voice_of_customer, manager]
- "Complete brand discovery with customer feedback for AI tools" → [market_research, competitor_intelligence, audience_persona, trend_cultural, voice_of_customer, manager]
- "Full brand analysis including voice of customer" → [market_research, competitor_intelligence, audience_persona, trend_cultural, voice_of_customer, manager]
- "Run brand discovery with customer sentiment analysis" → [market_research, competitor_intelligence, audience_persona, trend_cultural, voice_of_customer, manager]
- "Create a brand positioning strategy for our product" → [brand_positioning, manager]
- "Develop positioning statements and differentiation for our brand" → [brand_positioning, manager]
- "Generate a value proposition canvas and perceptual maps" → [brand_positioning, manager]
- "What is our unique value proposition and competitive positioning?" → [brand_positioning, manager]
- "Build brand positioning with market research context" → [market_research, competitor_intelligence, brand_positioning, manager]
- "Design a brand architecture for our product portfolio" → [brand_architecture, manager]
- "What brand structure should we use — branded house or house of brands?" → [brand_architecture, manager]
- "Create a brand hierarchy with naming conventions" → [brand_architecture, manager]
- "Build brand positioning and then design the brand architecture" → [brand_positioning, brand_architecture, manager]
- "Full brand strategy with positioning and architecture" → [brand_positioning, brand_architecture, manager]
""".strip()


def _build_compose_tool(catalog: list[dict]) -> dict:
    """Build the compose_pipeline function-calling tool from the current catalog."""
    valid_ids = [n["id"] for n in catalog]
    return {
        "function_declarations": [
            {
                "name": "compose_pipeline",
                "description": (
                    "Select and order the agent nodes needed to fulfill "
                    "the user's request. Nodes execute sequentially — each "
                    "node receives outputs from all previous nodes. Always "
                    "include 'manager' as the last node. Select the "
                    "minimum set needed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": valid_ids + ["manager"],
                            },
                            "description": (
                                "Ordered list of node IDs to execute. "
                                "Must end with 'manager'."
                            ),
                        },
                        "sub_tasks": {
                            "type": "string",
                            "description": (
                                "Optional JSON object mapping node_id to "
                                "sub-task description. Narrows each worker's "
                                "prompt to its specific responsibility. "
                                "Example: "
                                '{"odoo_sales_crm": "List open sales orders", '
                                '"odoo_hr": "List all employees"}'
                            ),
                        },
                        "dependencies": {
                            "type": "string",
                            "description": (
                                "Per-node prerequisites as a JSON object. "
                                "Keys are node_ids, values are comma-separated "
                                "node_ids that must complete first. Use empty "
                                "string for no dependencies. Nodes without "
                                "dependencies on each other run in parallel. "
                                "Example: "
                                '{"odoo_sales_crm": "", "odoo_inventory": "", '
                                '"manager": "odoo_sales_crm,odoo_inventory"}'
                            ),
                        },
                    },
                    "required": ["node_ids"],
                },
            }
        ]
    }


def _build_classify_tool() -> dict:
    """Build the select_pipeline function-calling tool for Tier 2."""
    valid_ids = [p["id"] for p in _PIPELINE_DESCRIPTIONS]
    return {
        "function_declarations": [
            {
                "name": "select_pipeline",
                "description": (
                    "Select the single best pipeline to handle the user's "
                    "request from the available options."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pipeline_id": {
                            "type": "string",
                            "enum": valid_ids,
                            "description": "The ID of the selected pipeline.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief reason for the selection.",
                        },
                    },
                    "required": ["pipeline_id", "reason"],
                },
            }
        ]
    }


def _build_system_prompt(catalog: list[dict]) -> str:
    """Build the base system prompt from the current catalog."""
    node_descriptions = "\n".join(
        f"- **{n['id']}**: {n['description']}" for n in catalog
    )
    return (
        "You are a pipeline orchestrator. Given a user prompt, select "
        "which agent nodes are needed and in what order. Each node's "
        "output flows to the next.\n\n"
        "Available nodes:\n"
        f"{node_descriptions}\n"
        "- **manager**: Terminal node that aggregates all outputs. "
        "Always include last.\n\n"
        "Rules:\n"
        "- Select the MINIMUM set of nodes needed\n"
        "- Nodes that need research input (blog_author, valuation_logic) "
        "must have a research node (default_agent or web_research) "
        "before them\n"
        "- social_promoter should come after content creation "
        "(blog_author)\n"
        "- Email campaigns, mass mailings, and marketing campaigns "
        "are Odoo ERP operations — use odoo_marketing, NOT "
        "social_promoter\n"
        "- social_promoter is ONLY for social media platforms "
        "(LinkedIn, Twitter, Facebook, Instagram)\n"
        "- For multi-domain Odoo tasks, use multiple persona-specific "
        "workers (e.g., odoo_sales_crm then odoo_marketing). Place "
        "data-gathering nodes before action nodes.\n"
        "- When using persona-specific Odoo workers, provide a sub_tasks "
        "object mapping each node_id to a focused sub-task description\n"
        "- When multiple Odoo workers are independent (don't need each "
        "other's output), provide dependencies so they can run in "
        "parallel. Workers that need prior output must list the "
        "producing node as a dependency.\n"
        "- For competitor analysis, competitive landscape, SWOT, "
        "competitive benchmarking, positioning gaps, or competitor "
        "profiling → ALWAYS use competitor_intelligence, NEVER "
        "gap_analyzer. gap_analyzer is ONLY for brand audits and "
        "ISO benchmark comparisons.\n"
        "- For buyer personas, target audience, customer segments, "
        "demographics, psychographics, buying journeys → use "
        "audience_persona. When combined with market research or "
        "competitor analysis, place audience_persona AFTER those nodes "
        "so it can use their output.\n"
        "- 'Brand discovery' prompts ALWAYS use the full 4-agent chain: "
        "[market_research, competitor_intelligence, audience_persona, "
        "trend_cultural, manager]. trend_cultural MUST be included for "
        "any brand discovery request.\n"
        "- Always end with manager\n"
        "- For document/RAG queries use default_agent, for web research "
        "use web_research"
    )


def _build_classify_system_prompt(needs_rag: bool = False) -> str:
    """Build the system prompt for Tier 2 LLM classification."""
    pipeline_list = "\n".join(
        f"- **{p['id']}**: {p['description']}" for p in _PIPELINE_DESCRIPTIONS
    )
    rag_hint = ""
    if needs_rag:
        rag_hint = (
            "\n\nIMPORTANT: The user has uploaded documents. Prefer "
            "RAG-based pipelines (rag-blog-social, rag-blog-authoring, "
            "general-chat) over web-research pipelines when the prompt "
            "references their documents."
        )
    return (
        "You are a pipeline router. Given a user prompt, select the "
        "single best pipeline from the options below.\n\n"
        "Available pipelines:\n"
        f"{pipeline_list}\n\n"
        "Routing rules:\n"
        "- Social platform mentions (LinkedIn, Twitter, etc.) → social-promotion\n"
        "- Blog/article writing → blog-authoring\n"
        "- Brand valuation, equity, ISO, royalty → iso-brand-equity\n"
        "- Competitor analysis, competitive gaps, SWOT, benchmarking → competitor-intelligence\n"
        "- Content calendar, editorial strategy → content-strategy\n"
        "- Document queries, RAG, summarize → general-chat\n"
        "- RAG + blog + social → rag-blog-social\n"
        "- RAG + blog (no social) → rag-blog-authoring\n"
        "- Brand positioning, market analysis → brand-analysis\n"
        "- Market research, market sizing, TAM, SAM, SOM, industry trends, "
        "growth potential, addressable market → market-research\n"
        "- Competitor profiling, SWOT analysis, competitive benchmarking, "
        "positioning gaps → competitor-intelligence\n"
        "- Market research + competitor analysis combined → "
        "market-research-competitor-intel\n"
        "- Buyer personas, target audience, customer segments, demographics, "
        "psychographics, buying journey → audience-persona\n"
        "- Full audience discovery (market + competitors + personas) → "
        "audience-persona-discovery\n"
        "- Brand discovery, full brand analysis, comprehensive brand "
        "intelligence → brand-discovery-full\n"
        "- Cultural trends, social media trends, viral content, "
        "generational preferences, emerging slang → trend-cultural-insights\n"
        "- Odoo ERP tasks, sales orders, inventory, HR, accounting, "
        "email campaigns, mass mailing, email marketing, marketing "
        "campaigns, newsletters → odoo-erp-operations\n"
        f"- Default for ambiguous queries → general-chat{rag_hint}"
    )


class PipelineComposer:
    """Dynamic pipeline composer using 3-tier routing: Gemini composition,
    LLM classification, and keyword fallback."""

    def __init__(self) -> None:
        self._catalog = NODE_CATALOG
        self._catalog_map = NODE_CATALOG_MAP
        self._tool = _build_compose_tool(self._catalog)
        self._base_system_prompt = _build_system_prompt(self._catalog)
        self._classify_tool = _build_classify_tool()

    async def compose(self, state: AgentState) -> dict[str, Any]:
        """Compose a pipeline for the given state.

        3-tier fallback chain:
          Tier 1: Gemini dynamic composition (context-enriched + retry)
          Tier 2: Gemini manifest classification (picks 1 of 9 pipelines)
          Tier 3: Keyword matching (stemming + RAG boost)

        Returns either:
            {"_composed_manifest": {...}} — Tier 1 succeeded
            {"resolved_manifest_id": "..."} — Tier 2 or 3
        """
        # Tier 1: Enhanced Gemini dynamic composition
        if settings.GOOGLE_API_KEY:
            try:
                compose_result = await self._gemini_compose(state)
                if compose_result:
                    node_ids, sub_tasks, dependencies = compose_result
                    node_ids = self._apply_rewrite_rules(node_ids, state)
                    manifest = self._build_manifest(node_ids, sub_tasks, dependencies)
                    logger.info(
                        "Gemini composed pipeline: %s",
                        " → ".join(node_ids),
                    )
                    return {"_composed_manifest": manifest}
            except Exception:
                logger.warning(
                    "Tier 1 failed, trying LLM classification",
                    exc_info=True,
                )

        # Tier 2: LLM manifest classification
        if settings.GOOGLE_API_KEY:
            try:
                manifest_id = await self._llm_classify_fallback(state)
                if manifest_id:
                    # Apply manifest-level rewrite for known misroutes
                    if manifest_id == "competitor-audit":
                        prompt = (state.get("input_prompt") or "").lower()
                        competitor_signals = {
                            "competitor",
                            "competitors",
                            "competitive",
                            "swot",
                            "benchmark",
                            "benchmarking",
                            "positioning gap",
                            "competitive landscape",
                        }
                        if any(s in prompt for s in competitor_signals):
                            logger.info(
                                "Tier 2 rewrite: competitor-audit → "
                                "competitor-intelligence"
                            )
                            manifest_id = "competitor-intelligence"
                    logger.info("LLM classify selected: %s", manifest_id)
                    return {"resolved_manifest_id": manifest_id}
            except Exception:
                logger.warning(
                    "Tier 2 failed, falling back to keywords",
                    exc_info=True,
                )

        # Tier 3: Keyword matching
        resolved_id = self._keyword_fallback(state)
        logger.info("Keyword fallback resolved to: %s", resolved_id)
        return {"resolved_manifest_id": resolved_id}

    # ── Tier 1: Gemini Dynamic Composition ──

    def _enrich_system_prompt(self, state: AgentState) -> str:
        """Append company context, RAG hints, manifest reference, and
        few-shot examples to the base system prompt."""
        parts = [self._base_system_prompt]
        ctx = state.get("input_context") or {}

        # Company context (sanitized to prevent prompt injection)
        company_name = ctx.get("company_name")
        sector = ctx.get("sector")
        brand_voice = ctx.get("brand_voice")
        if company_name or sector or brand_voice:
            context_lines = []
            if company_name:
                context_lines.append(
                    f"Company: {sanitize_ai_prompt(str(company_name))[:200]}"
                )
            if sector:
                context_lines.append(f"Sector: {sanitize_ai_prompt(str(sector))[:200]}")
            if brand_voice:
                context_lines.append(
                    f"Brand voice: {sanitize_ai_prompt(str(brand_voice))[:200]}"
                )
            parts.append("\n\nCompany context:\n" + "\n".join(context_lines))

        # RAG hint
        if ctx.get("needs_rag"):
            parts.append(
                "\n\nIMPORTANT: The user has uploaded documents. Prefer "
                "default_agent over web_research when the prompt "
                "references their documents or knowledge base."
            )

        # Manifest reference
        available = state.get("available_manifests") or []
        if available:
            manifest_lines = "\n".join(
                f"- {m['pipeline_id']}: {m.get('description', m.get('name', ''))}"
                for m in available
            )
            parts.append(f"\n\nAvailable pipeline manifests:\n{manifest_lines}")

        # Few-shot examples
        parts.append(f"\n\n{_FEW_SHOT_EXAMPLES}")

        return "".join(parts)

    @staticmethod
    def _build_user_message(state: AgentState) -> str:
        """Build the user-facing message for Gemini, including recent
        chat history when available."""
        prompt = sanitize_ai_prompt(state.get("input_prompt", ""))
        ctx = state.get("input_context") or {}
        chat_history = ctx.get("chat_history")

        if isinstance(chat_history, list):
            # Include last 3 messages for context
            recent = chat_history[-3:]
            history_lines: list[str] = []
            for raw_msg in recent:
                if not isinstance(raw_msg, dict):
                    continue
                role = str(raw_msg.get("role", "user") or "user")
                raw_content = raw_msg.get("content", "")
                if raw_content is None:
                    continue
                content = sanitize_ai_prompt(str(raw_content))
                if not content:
                    continue
                # Truncate overly long history messages
                history_lines.append(f"  {role}: {content[:1000]}")

            if history_lines:
                history_text = "\n".join(history_lines)
                return (
                    f"Recent conversation:\n{history_text}\n\n"
                    f"Current request: {prompt}"
                )

        return prompt

    async def _gemini_compose(
        self, state: AgentState
    ) -> tuple[list[str], dict[str, str], dict[str, list[str]]] | None:
        """Use Gemini function-calling to select and order nodes.

        Retries up to GEMINI_COMPOSE_MAX_RETRIES times with linear
        backoff (delay * attempt) on failure.
        """
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)

        system_prompt = self._enrich_system_prompt(state)
        user_message = self._build_user_message(state)

        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            system_instruction=system_prompt,
            tools=[self._tool],
        )

        max_retries = settings.GEMINI_COMPOSE_MAX_RETRIES
        last_exc: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await model.generate_content_async(
                    user_message,
                    tool_config={"function_calling_config": {"mode": "ANY"}},
                )

                # Extract the function call
                for part in response.parts:
                    if fn := part.function_call:
                        if fn.name == "compose_pipeline":
                            raw_ids = list(fn.args.get("node_ids", []))
                            # sub_tasks comes as JSON string
                            raw_st = fn.args.get("sub_tasks", "")
                            if isinstance(raw_st, str) and raw_st.strip():
                                try:
                                    import json

                                    raw_sub_tasks = json.loads(raw_st)
                                    if not isinstance(raw_sub_tasks, dict):
                                        raw_sub_tasks = {}
                                except (json.JSONDecodeError, ValueError):
                                    raw_sub_tasks = {}
                            elif isinstance(raw_st, dict):
                                raw_sub_tasks = raw_st
                            else:
                                raw_sub_tasks = {}
                            # dependencies comes as JSON string
                            raw_dep_str = fn.args.get("dependencies", "")
                            if isinstance(raw_dep_str, str) and raw_dep_str.strip():
                                try:
                                    import json

                                    raw_dep_obj = json.loads(raw_dep_str)
                                    if not isinstance(raw_dep_obj, dict):
                                        raw_dep_obj = {}
                                except (json.JSONDecodeError, ValueError):
                                    raw_dep_obj = {}
                            elif isinstance(raw_dep_str, dict):
                                raw_dep_obj = raw_dep_str
                            else:
                                raw_dep_obj = {}
                            # Normalise dep values defensively:
                            # accept list[str] or comma-separated string.
                            deps: dict[str, list[str]] = {}
                            for k, v in raw_dep_obj.items():
                                if isinstance(v, str):
                                    deps[k] = [
                                        s.strip() for s in v.split(",") if s.strip()
                                    ]
                                elif isinstance(v, list) and all(
                                    isinstance(item, str) for item in v
                                ):
                                    deps[k] = v
                                else:
                                    logger.warning(
                                        "Ignoring malformed dependency value "
                                        "for %s: %r",
                                        k,
                                        v,
                                    )
                                    deps[k] = []
                            result = self._validate_node_ids(raw_ids)
                            if result:
                                logger.info(
                                    "Gemini composed pipeline (attempt %d): %s",
                                    attempt + 1,
                                    " → ".join(result),
                                )
                                return result, raw_sub_tasks, deps

                logger.warning(
                    "Gemini did not return a compose_pipeline call " "(attempt %d)",
                    attempt + 1,
                )
                return None

            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = settings.GEMINI_COMPOSE_RETRY_DELAY * (attempt + 1)
                    logger.warning(
                        "Gemini composition attempt %d failed, "
                        "retrying in %.1fs: %s",
                        attempt + 1,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

        # Exhausted retries — re-raise so compose() catches it
        raise last_exc  # type: ignore[misc]

    # ── Tier 2: LLM Manifest Classification ──

    async def _llm_classify_fallback(self, state: AgentState) -> str | None:
        """Use a lightweight Gemini call to select ONE pipeline_id
        from the 9 available manifests."""
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)

        ctx = state.get("input_context") or {}
        needs_rag = bool(ctx.get("needs_rag"))
        system_prompt = _build_classify_system_prompt(needs_rag)
        prompt = sanitize_ai_prompt(state.get("input_prompt", ""))

        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            system_instruction=system_prompt,
            tools=[self._classify_tool],
        )

        response = await model.generate_content_async(
            prompt,
            tool_config={"function_calling_config": {"mode": "ANY"}},
        )

        valid_ids = {p["id"] for p in _PIPELINE_DESCRIPTIONS}

        for part in response.parts:
            if fn := part.function_call:
                if fn.name == "select_pipeline":
                    pipeline_id = fn.args.get("pipeline_id", "")
                    reason = fn.args.get("reason", "")
                    if pipeline_id in valid_ids:
                        logger.info(
                            "LLM classify selected '%s': %s",
                            pipeline_id,
                            reason,
                        )
                        return pipeline_id
                    logger.warning(
                        "LLM classify returned invalid pipeline_id: %s",
                        pipeline_id,
                    )
                    return None

        logger.warning("LLM classify did not return a select_pipeline call")
        return None

    # ── Tier 3: Keyword Fallback ──

    @staticmethod
    def _keyword_fallback(state: AgentState) -> str:
        """Fall back to improved keyword matching with stemming and
        RAG boosting (reuses shared keyword_match function)."""
        return keyword_match(state)

    # ── Shared helpers ──

    @staticmethod
    def _apply_rewrite_rules(node_ids: list[str], state: AgentState) -> list[str]:
        """Deterministic post-composition rewrites.

        Fixes known LLM routing mistakes that can't be reliably prevented
        via system prompt alone.
        """
        if "gap_analyzer" not in node_ids:
            return node_ids

        prompt = (state.get("input_prompt") or "").lower()
        competitor_signals = {
            "competitor",
            "competitors",
            "competitive",
            "swot",
            "benchmark",
            "benchmarking",
            "positioning gap",
            "competitive landscape",
            "competitor profiling",
            "competitive intelligence",
        }
        if any(signal in prompt for signal in competitor_signals):
            rewritten = [
                "competitor_intelligence" if nid == "gap_analyzer" else nid
                for nid in node_ids
            ]
            # Deduplicate in case both were already present
            seen: set[str] = set()
            deduped: list[str] = []
            for nid in rewritten:
                if nid not in seen:
                    seen.add(nid)
                    deduped.append(nid)
            logger.info(
                "Rewrite rule applied: gap_analyzer → competitor_intelligence "
                "(prompt contains competitor signals)"
            )
            return deduped

        return node_ids

    def _validate_node_ids(self, raw_ids: list[str]) -> list[str] | None:
        """Validate and sanitize node IDs from Gemini response."""
        valid_ids = set(self._catalog_map.keys()) | {"manager"}
        filtered = [nid for nid in raw_ids if nid in valid_ids]

        if not filtered:
            return None

        # Ensure manager is always last
        if "manager" in filtered and filtered[-1] != "manager":
            filtered.remove("manager")
            filtered.append("manager")
        elif "manager" not in filtered:
            filtered.append("manager")

        return filtered

    def _build_manifest(
        self,
        node_ids: list[str],
        sub_tasks: dict[str, str] | None = None,
        dependencies: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """Build a complete manifest dict from an ordered list of node IDs.

        When *sub_tasks* is provided, each node's config is enriched with
        a ``sub_task`` key containing the narrowed prompt for that node.

        When *dependencies* is provided and non-empty, edges are derived
        from the dependency graph (enabling parallel execution of
        independent nodes). Otherwise falls back to sequential wiring.
        """
        sub_tasks = sub_tasks or {}
        nodes: list[dict[str, Any]] = []
        for nid in node_ids:
            if nid == "manager":
                nodes.append(
                    {
                        "id": "manager",
                        "type": "internal",
                        "handler": "ManagerNode",
                    }
                )
                continue

            entry = self._catalog_map[nid]
            node_def: dict[str, Any] = {"id": nid, "type": entry["type"]}
            if entry["type"] == "internal":
                node_def["handler"] = entry["handler"]
            else:
                node_def["url"] = entry["url"]
            # Merge catalog config + sub_task
            config = dict(entry.get("config") or {})
            if nid in sub_tasks:
                config["sub_task"] = sub_tasks[nid]
            if config:
                node_def["config"] = config
            nodes.append(node_def)

        # Build edges from dependencies or fall back to sequential
        node_id_set = set(node_ids)
        if dependencies:
            # Filter to only valid node IDs
            edges: list[list[str]] = [
                [dep, nid]
                for nid, deps in dependencies.items()
                if nid in node_id_set
                for dep in deps
                if dep in node_id_set
            ]
            # Auto-wire manager: if manager is in node_ids but not in
            # dependencies, add edges from all non-manager nodes to manager
            if "manager" in node_id_set and "manager" not in dependencies:
                for nid in node_ids:
                    if nid != "manager":
                        edge = [nid, "manager"]
                        if edge not in edges:
                            edges.append(edge)
        else:
            # Sequential fallback: n1→n2→n3→...
            edges = [[node_ids[i], node_ids[i + 1]] for i in range(len(node_ids) - 1)]

        return {
            "nodes": nodes,
            "edges": edges,
            "global_config": {
                "model": "gemini-2.0-flash",
                "temperature": 0.7,
            },
        }
