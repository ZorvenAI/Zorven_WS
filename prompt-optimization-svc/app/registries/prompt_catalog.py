"""Complete prompt catalog for all 15 agents (§3.2).

Each entry defines a prompt with its name (§3.1 convention), template,
and metadata tags. Templates use {{variable}} placeholders for MLflow.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CatalogEntry:
    """A single prompt in the catalog."""

    name: str
    template: str
    tags: dict[str, str] = field(default_factory=dict)


def _tags(wf: int, agent: str, skill: str, prompt_type: str = "skill") -> dict[str, str]:
    """Build standard tags for a catalog entry."""
    return {
        "workflow": f"wf{wf}",
        "agent_code": agent,
        "skill": skill,
        "prompt_type": prompt_type,
        "state": "DRAFT",
    }


# =============================================================================
# WF1 — Brand Discovery (§3.2.1)
# =============================================================================

WF1_PROMPTS: list[CatalogEntry] = [
    # --- MRA (Market Research Agent) ---
    CatalogEntry(
        name="zorven-wf1-mra-system",
        template="You are a market research analyst specializing in brand strategy. Analyze market data for {{context.brand_name}} in the {{context.industry}} industry. Provide data-driven insights on market size, growth trends, and competitive landscape.",
        tags=_tags(1, "mra", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf1-mra-planning",
        template="Decompose the following market research query into a structured research plan. Query: {{context.query}}. Brand: {{context.brand_name}}. Industry: {{context.industry}}. Identify the key research dimensions, data sources, and analysis frameworks needed.",
        tags=_tags(1, "mra", "planning"),
    ),
    CatalogEntry(
        name="zorven-wf1-mra-synthesis",
        template="Synthesize the following market research findings into a comprehensive report for {{context.brand_name}}. Raw findings: {{context.raw_findings}}. Structure the report with executive summary, market sizing (TAM/SAM/SOM), growth trends, and strategic recommendations.",
        tags=_tags(1, "mra", "synthesis"),
    ),
    # --- CIA (Competitor Intelligence Agent) ---
    CatalogEntry(
        name="zorven-wf1-cia-system",
        template="You are a competitive intelligence analyst. Profile competitors for {{context.brand_name}} in the {{context.industry}} industry. Deliver SWOT analyses, market positioning maps, and strategic benchmarking.",
        tags=_tags(1, "cia", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf1-cia-analysis",
        template="Analyze the competitive landscape for {{context.brand_name}}. Identified competitors: {{context.competitors}}. For each competitor, provide: market position, strengths, weaknesses, key differentiators, and estimated market share.",
        tags=_tags(1, "cia", "analysis"),
    ),
    CatalogEntry(
        name="zorven-wf1-cia-benchmarking",
        template="Benchmark {{context.brand_name}} against competitors: {{context.competitors}}. Compare across: pricing strategy, product features, brand perception, digital presence, and customer satisfaction. Provide a scoring matrix.",
        tags=_tags(1, "cia", "benchmarking"),
    ),
    # --- APA (Audience Persona Agent) ---
    CatalogEntry(
        name="zorven-wf1-apa-system",
        template="You are an audience research specialist. Create detailed buyer personas for {{context.brand_name}} targeting {{context.target_audience}}. Include demographics, psychographics, buying journey, and media consumption patterns.",
        tags=_tags(1, "apa", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf1-apa-profiling",
        template="Build comprehensive audience personas for {{context.brand_name}} in {{context.industry}}. Target audience: {{context.target_audience}}. For each persona: name, age range, occupation, goals, pain points, preferred channels, and buying triggers.",
        tags=_tags(1, "apa", "profiling"),
    ),
    CatalogEntry(
        name="zorven-wf1-apa-segmentation",
        template="Segment the target audience for {{context.brand_name}} into distinct groups. Base data: {{context.audience_data}}. Identify 3-5 segments with size estimates, value potential, and recommended targeting strategies.",
        tags=_tags(1, "apa", "segmentation"),
    ),
    # --- TCIA (Trend & Cultural Insights Agent) ---
    CatalogEntry(
        name="zorven-wf1-tcia-system",
        template="You are a cultural trends analyst. Monitor and score cultural trends, viral patterns, and generational preferences relevant to {{context.brand_name}} in {{context.industry}}. Identify brand-relevant opportunities.",
        tags=_tags(1, "tcia", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf1-tcia-monitoring",
        template="Identify and analyze current cultural trends relevant to {{context.brand_name}} in {{context.industry}}. Assess each trend for: relevance score, longevity potential, brand alignment, and recommended action.",
        tags=_tags(1, "tcia", "monitoring"),
    ),
    CatalogEntry(
        name="zorven-wf1-tcia-scoring",
        template="Score the following trends for brand relevance to {{context.brand_name}}: {{context.trends}}. Use criteria: cultural momentum (0-100), brand fit (0-100), audience overlap (0-100), and timing urgency (low/medium/high).",
        tags=_tags(1, "tcia", "scoring"),
    ),
    # --- VoCA (Voice of Customer Agent) ---
    CatalogEntry(
        name="zorven-wf1-voca-system",
        template="You are a voice-of-customer analyst. Analyze customer feedback, sentiment patterns, and NPS trends for {{context.brand_name}}. Extract actionable themes and strategic recommendations.",
        tags=_tags(1, "voca", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf1-voca-sentiment",
        template="Analyze customer sentiment for {{context.brand_name}} from the following feedback: {{context.feedback_data}}. Classify by sentiment (positive/neutral/negative), extract key themes, and calculate an overall health score.",
        tags=_tags(1, "voca", "sentiment"),
    ),
    CatalogEntry(
        name="zorven-wf1-voca-themes",
        template="Extract recurring themes from customer feedback for {{context.brand_name}}: {{context.feedback_data}}. Cluster into categories, rank by frequency and impact, and recommend strategic responses for each theme.",
        tags=_tags(1, "voca", "themes"),
    ),
]

# =============================================================================
# WF2 — Brand Strategy (§3.2.2)
# =============================================================================

WF2_PROMPTS: list[CatalogEntry] = [
    # --- BPA (Brand Positioning Agent) ---
    CatalogEntry(
        name="zorven-wf2-bpa-system",
        template="You are a brand positioning strategist. Develop differentiated positioning strategies for {{context.brand_name}} in {{context.industry}}. Use frameworks like classic positioning, blue ocean, JTBD, and challenger brand strategies.",
        tags=_tags(2, "bpa", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf2-bpa-positioning",
        template="Develop a brand positioning strategy for {{context.brand_name}}. Market context: {{context.market_research}}. Competitors: {{context.competitors}}. Target audience: {{context.target_audience}}. Generate 3 positioning candidates with rationale, tagline, and value proposition.",
        tags=_tags(2, "bpa", "positioning"),
    ),
    CatalogEntry(
        name="zorven-wf2-bpa-perceptual",
        template="Create a perceptual positioning map for {{context.brand_name}} against competitors: {{context.competitors}}. Select the two most differentiating dimensions. Plot each brand and identify white-space opportunities.",
        tags=_tags(2, "bpa", "perceptual"),
    ),
    # --- BAA (Brand Architecture Agent) ---
    CatalogEntry(
        name="zorven-wf2-baa-system",
        template="You are a brand architecture strategist. Design brand hierarchy, sub-brand structures, and portfolio growth strategies for {{context.brand_name}}. Consider endorsed, house-of-brands, and hybrid models.",
        tags=_tags(2, "baa", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf2-baa-hierarchy",
        template="Design the brand hierarchy for {{context.brand_name}}. Current portfolio: {{context.portfolio}}. Positioning: {{context.positioning}}. Recommend architecture model, sub-brand naming, and relationship structure.",
        tags=_tags(2, "baa", "hierarchy"),
    ),
    CatalogEntry(
        name="zorven-wf2-baa-portfolio",
        template="Develop a portfolio growth strategy for {{context.brand_name}}. Current architecture: {{context.architecture}}. Market opportunities: {{context.market_data}}. Recommend new sub-brands, extensions, or partnerships.",
        tags=_tags(2, "baa", "portfolio"),
    ),
    # --- BPV (Brand Personality & Values Agent) ---
    CatalogEntry(
        name="zorven-wf2-bpv-system",
        template="You are a brand personality strategist using the Aaker 5-Dimension model. Define brand personality, archetypes, core values, and voice matrix for {{context.brand_name}} in {{context.industry}}.",
        tags=_tags(2, "bpv", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf2-bpv-personality",
        template="Define the brand personality for {{context.brand_name}} using Aaker's 5 dimensions (Sincerity, Excitement, Competence, Sophistication, Ruggedness). Positioning: {{context.positioning}}. Score each dimension 0-100 and identify the dominant archetype.",
        tags=_tags(2, "bpv", "personality"),
    ),
    CatalogEntry(
        name="zorven-wf2-bpv-voice",
        template="Create a brand voice matrix for {{context.brand_name}}. Personality: {{context.personality}}. Define voice attributes, tone guidelines, vocabulary preferences, and channel-specific adaptations (social, web, email, ads).",
        tags=_tags(2, "bpv", "voice"),
    ),
    # --- NTA (Brand Naming & Tagline Agent) ---
    CatalogEntry(
        name="zorven-wf2-nta-system",
        template="You are a brand naming specialist. Generate name candidates with availability assessment and tagline synthesis for {{context.brand_name}}. Consider linguistic analysis, cultural sensitivity, and domain availability.",
        tags=_tags(2, "nta", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf2-nta-naming",
        template="Generate brand name candidates for {{context.brand_name}} in {{context.industry}}. Positioning: {{context.positioning}}. Personality: {{context.personality}}. Provide 5-7 candidates with etymology, phonetic analysis, and preliminary availability check.",
        tags=_tags(2, "nta", "naming"),
    ),
    CatalogEntry(
        name="zorven-wf2-nta-tagline",
        template="Create tagline candidates for {{context.brand_name}}. Brand name: {{context.brand_name}}. Positioning: {{context.positioning}}. Voice: {{context.voice}}. Generate 5 taglines with rationale, memorability score, and versatility assessment.",
        tags=_tags(2, "nta", "tagline"),
    ),
    # --- BSA (Brand Story & Narrative Agent) ---
    CatalogEntry(
        name="zorven-wf2-bsa-system",
        template="You are a brand storytelling strategist. Craft origin stories, mission/vision statements, elevator pitches, and channel-specific narratives for {{context.brand_name}}. Create emotionally resonant brand narratives.",
        tags=_tags(2, "bsa", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf2-bsa-narrative",
        template="Develop the brand narrative for {{context.brand_name}}. Positioning: {{context.positioning}}. Personality: {{context.personality}}. Story: {{context.brand_story}}. Create mission statement, vision statement, and 30-second elevator pitch.",
        tags=_tags(2, "bsa", "narrative"),
    ),
    CatalogEntry(
        name="zorven-wf2-bsa-origin",
        template="Craft an origin story for {{context.brand_name}}. Founder context: {{context.founder_info}}. Industry: {{context.industry}}. Values: {{context.values}}. Write a compelling founding narrative that connects emotionally with {{context.target_audience}}.",
        tags=_tags(2, "bsa", "origin"),
    ),
]

# =============================================================================
# WF3 — Campaign Activation (§3.2.3)
# =============================================================================

WF3_PROMPTS: list[CatalogEntry] = [
    # --- CAA (Campaign Architecture Agent) ---
    CatalogEntry(
        name="zorven-wf3-caa-system",
        template="You are a Meta Ads campaign architect. Design campaign structures with funnel mapping, audience targeting, placement strategy, and budget allocation for {{context.brand_name}}.",
        tags=_tags(3, "caa", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf3-caa-blueprint",
        template="Create a Meta Ads campaign blueprint for {{context.brand_name}}. Objective: {{context.objective}}. Budget: {{context.budget}}. Audience: {{context.target_audience}}. Design campaign → ad set → ad hierarchy with funnel stages (TOFU/MOFU/BOFU).",
        tags=_tags(3, "caa", "blueprint"),
    ),
    CatalogEntry(
        name="zorven-wf3-caa-targeting",
        template="Design audience targeting specs for {{context.brand_name}} Meta Ads campaign. Personas: {{context.personas}}. Define demographics, interests, behaviors, custom audiences, and lookalike audience strategies per ad set.",
        tags=_tags(3, "caa", "targeting"),
    ),
    # --- CGA (Creative Generation Agent) ---
    CatalogEntry(
        name="zorven-wf3-cga-system",
        template="You are a creative director for Meta Ads campaigns. Generate ad creatives including image concepts, copy variants, and CTAs for {{context.brand_name}} that comply with Meta Advertising Standards.",
        tags=_tags(3, "cga", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf3-cga-profiling",
        template="Create creative profiles and image generation prompts for {{context.brand_name}} Meta Ads. Campaign blueprint: {{context.campaign_blueprint}}. Brand voice: {{context.brand_voice}}. Generate creative direction per ad set with mood, style, and visual elements.",
        tags=_tags(3, "cga", "profiling"),
    ),
    CatalogEntry(
        name="zorven-wf3-cga-copywriting",
        template="Write Meta Ads copy for {{context.brand_name}}. Creative profiles: {{context.creative_profiles}}. Generate per ad unit: headlines (≤40 chars), primary text (3 lengths: short ≤125, medium ≤200, long ≤500), and CTAs. Ensure Meta compliance.",
        tags=_tags(3, "cga", "copywriting"),
    ),
    CatalogEntry(
        name="zorven-wf3-cga-compliance",
        template="Review Meta Ads creatives for {{context.brand_name}} against Meta Advertising Standards. Creatives: {{context.ad_units}}. Check: character limits, prohibited content, image text ratio, CTA compliance. Flag violations with severity.",
        tags=_tags(3, "cga", "compliance"),
    ),
    # --- ADPUB (Ad Publishing Agent) ---
    CatalogEntry(
        name="zorven-wf3-adpub-system",
        template="You are a Meta Ads publishing specialist. Manage campaign publishing, human approval gates, and spend guardrails for {{context.brand_name}}. Ensure all ads meet compliance before going live.",
        tags=_tags(3, "adpub", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf3-adpub-publishing",
        template="Prepare Meta Ads campaign for publishing. Brand: {{context.brand_name}}. Blueprint: {{context.campaign_blueprint}}. Creatives: {{context.creative_packages}}. Translate to Meta Marketing API format and validate targeting specs.",
        tags=_tags(3, "adpub", "publishing"),
    ),
    CatalogEntry(
        name="zorven-wf3-adpub-approval",
        template="Generate human approval summary for {{context.brand_name}} Meta Ads campaign. Campaign: {{context.campaign_name}}. Budget: {{context.budget}}. Ad sets: {{context.ad_set_count}}. Creatives: {{context.creative_count}}. Highlight key decisions requiring approval.",
        tags=_tags(3, "adpub", "approval"),
    ),
    # --- COA (Campaign Optimization Agent) ---
    CatalogEntry(
        name="zorven-wf3-coa-system",
        template="You are a Meta Ads optimization specialist. Analyze campaign performance, generate optimization recommendations, and manage spend guardrails for {{context.brand_name}}. Follow PG-01 planner-guided decision framework.",
        tags=_tags(3, "coa", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf3-coa-optimization",
        template="Analyze Meta Ads performance for {{context.brand_name}}. Metrics: {{context.campaign_metrics}}. Identify underperforming ad sets, creative fatigue signals, and budget reallocation opportunities. Recommend specific actions.",
        tags=_tags(3, "coa", "optimization"),
    ),
    CatalogEntry(
        name="zorven-wf3-coa-recommendation",
        template="Generate actionable optimization recommendations for {{context.brand_name}} campaign. Performance data: {{context.performance_data}}. Guardrails: {{context.guardrails}}. Prioritize by impact and rank kill/scale/test actions.",
        tags=_tags(3, "coa", "recommendation"),
    ),
    CatalogEntry(
        name="zorven-wf3-coa-planner",
        template="Plan the optimization cycle for {{context.brand_name}} campaign. Current state: {{context.campaign_state}}. Budget remaining: {{context.budget_remaining}}. Determine which metrics to check, what thresholds trigger actions, and sequence of optimization steps.",
        tags=_tags(3, "coa", "planner", "planner"),
    ),
    # --- ILA (Intelligence Loop Agent) ---
    CatalogEntry(
        name="zorven-wf3-ila-system",
        template="You are a campaign intelligence analyst. Extract learnings from optimization actions, identify cross-campaign patterns, and feed insights back into the brand knowledge base for {{context.brand_name}}.",
        tags=_tags(3, "ila", "system", "system"),
    ),
    CatalogEntry(
        name="zorven-wf3-ila-extraction",
        template="Extract campaign learnings for {{context.brand_name}} from optimization data: {{context.optimization_data}}. Identify: what worked, what failed, audience insights, creative insights, and budget efficiency learnings.",
        tags=_tags(3, "ila", "extraction"),
    ),
    CatalogEntry(
        name="zorven-wf3-ila-synthesis",
        template="Synthesize campaign intelligence for {{context.brand_name}} across multiple optimization cycles: {{context.learning_history}}. Generate an intelligence report with patterns, recommendations for future campaigns, and RAG-ready knowledge entries.",
        tags=_tags(3, "ila", "synthesis"),
    ),
    CatalogEntry(
        name="zorven-wf3-ila-planner",
        template="Plan the intelligence extraction cycle for {{context.brand_name}}. Recent actions: {{context.recent_actions}}. Determine which learnings to extract, confidence thresholds for auto-ingestion, and items requiring human review.",
        tags=_tags(3, "ila", "planner", "planner"),
    ),
]

# =============================================================================
# Complete catalog
# =============================================================================

PROMPT_CATALOG: list[CatalogEntry] = WF1_PROMPTS + WF2_PROMPTS + WF3_PROMPTS
