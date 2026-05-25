"""
Golden dataset seed data for GEPA prompt evaluation.

~260 examples across 15 agents, 12 industry verticals, 4 source types.
Uses generator pattern with _make_example() helper to avoid repetition.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenExample:
    prompt_name: str
    agent_code: str
    input_context: dict[str, Any]
    expected_output: str
    source: str  # "manual" | "synthetic" | "mined" | "adversarial"
    metadata_extra: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Industry verticals and brand archetypes
# ---------------------------------------------------------------------------

INDUSTRIES = [
    "SaaS/Technology",
    "E-commerce/Retail",
    "Healthcare/Wellness",
    "Financial Services",
    "Education/EdTech",
    "Food & Beverage",
    "Real Estate",
    "Travel & Hospitality",
    "Fashion & Apparel",
    "Professional Services",
    "Automotive",
    "Entertainment/Media",
]

_BRANDS: dict[str, dict[str, str]] = {
    "SaaS/Technology": {
        "brand_name": "CloudPulse",
        "product_description": "AI-powered cloud infrastructure monitoring platform",
        "target_audience": "DevOps engineers and CTOs at mid-market SaaS companies",
        "brand_voice": "Authoritative yet approachable, data-driven",
        "budget_range": "$50K-150K/quarter",
    },
    "E-commerce/Retail": {
        "brand_name": "ShopVibe",
        "product_description": "Personalized e-commerce storefront builder with AI recommendations",
        "target_audience": "D2C brand founders and small retail business owners",
        "brand_voice": "Energetic, trend-savvy, empowering",
        "budget_range": "$20K-80K/quarter",
    },
    "Healthcare/Wellness": {
        "brand_name": "VitaPath",
        "product_description": "Telehealth platform connecting patients with holistic wellness practitioners",
        "target_audience": "Health-conscious adults 30-55 seeking integrative care",
        "brand_voice": "Warm, trustworthy, evidence-based",
        "budget_range": "$30K-100K/quarter",
    },
    "Financial Services": {
        "brand_name": "FinEdge",
        "product_description": "Robo-advisory platform for millennials with ESG-focused portfolios",
        "target_audience": "Millennials and Gen-Z investors with $10K-500K in assets",
        "brand_voice": "Confident, transparent, jargon-free",
        "budget_range": "$80K-250K/quarter",
    },
    "Education/EdTech": {
        "brand_name": "LearnSphere",
        "product_description": "Adaptive learning platform for K-12 with AI tutoring",
        "target_audience": "School districts, parents, and education administrators",
        "brand_voice": "Encouraging, inclusive, research-backed",
        "budget_range": "$25K-90K/quarter",
    },
    "Food & Beverage": {
        "brand_name": "HarvestTable",
        "product_description": "Farm-to-table meal kit delivery with seasonal menus",
        "target_audience": "Urban professionals and families who value organic food",
        "brand_voice": "Rustic, wholesome, community-driven",
        "budget_range": "$15K-60K/quarter",
    },
    "Real Estate": {
        "brand_name": "NestFinder",
        "product_description": "AI-powered property matching platform for first-time buyers",
        "target_audience": "First-time homebuyers aged 25-40 in metro areas",
        "brand_voice": "Reassuring, knowledgeable, milestone-oriented",
        "budget_range": "$40K-120K/quarter",
    },
    "Travel & Hospitality": {
        "brand_name": "WanderCraft",
        "product_description": "Curated boutique travel experiences with local guides",
        "target_audience": "Affluent travelers seeking authentic cultural experiences",
        "brand_voice": "Inspiring, sophisticated, adventurous",
        "budget_range": "$35K-110K/quarter",
    },
    "Fashion & Apparel": {
        "brand_name": "ThreadEthos",
        "product_description": "Sustainable fashion marketplace for ethical brands",
        "target_audience": "Eco-conscious consumers aged 22-45",
        "brand_voice": "Stylish, principled, forward-thinking",
        "budget_range": "$30K-100K/quarter",
    },
    "Professional Services": {
        "brand_name": "StrataBridge",
        "product_description": "AI-augmented management consulting for mid-market firms",
        "target_audience": "C-suite executives at companies with $10M-500M revenue",
        "brand_voice": "Polished, insightful, results-oriented",
        "budget_range": "$60K-200K/quarter",
    },
    "Automotive": {
        "brand_name": "VoltDrive",
        "product_description": "Electric vehicle subscription service with flexible terms",
        "target_audience": "Urban commuters considering EV transition",
        "brand_voice": "Bold, innovative, eco-forward",
        "budget_range": "$100K-300K/quarter",
    },
    "Entertainment/Media": {
        "brand_name": "StoryForge",
        "product_description": "AI-assisted screenwriting and content production platform",
        "target_audience": "Independent filmmakers and content creators",
        "brand_voice": "Creative, collaborative, boundary-pushing",
        "budget_range": "$20K-75K/quarter",
    },
}

MATURITIES = ["new", "emerging", "established"]

# ---------------------------------------------------------------------------
# Agent prompt definitions
# ---------------------------------------------------------------------------

AGENT_PROMPTS: dict[str, list[str]] = {
    "MRA": [
        "zorven-wf1-mra-system",
        "zorven-wf1-mra-planning",
        "zorven-wf1-mra-synthesis",
    ],
    "CIA": [
        "zorven-wf1-cia-system",
        "zorven-wf1-cia-analysis",
        "zorven-wf1-cia-benchmarking",
    ],
    "APA": [
        "zorven-wf1-apa-system",
        "zorven-wf1-apa-profiling",
        "zorven-wf1-apa-segmentation",
    ],
    "TCIA": [
        "zorven-wf1-tcia-system",
        "zorven-wf1-tcia-monitoring",
        "zorven-wf1-tcia-scoring",
    ],
    "VoCA": [
        "zorven-wf1-voca-system",
        "zorven-wf1-voca-sentiment",
        "zorven-wf1-voca-themes",
    ],
    "BPA": [
        "zorven-wf2-bpa-system",
        "zorven-wf2-bpa-positioning",
        "zorven-wf2-bpa-perceptual",
    ],
    "BAA": [
        "zorven-wf2-baa-system",
        "zorven-wf2-baa-hierarchy",
        "zorven-wf2-baa-portfolio",
    ],
    "BPV": [
        "zorven-wf2-bpv-system",
        "zorven-wf2-bpv-personality",
        "zorven-wf2-bpv-voice",
    ],
    "NTA": [
        "zorven-wf2-nta-system",
        "zorven-wf2-nta-naming",
        "zorven-wf2-nta-tagline",
    ],
    "BSA": [
        "zorven-wf2-bsa-system",
        "zorven-wf2-bsa-narrative",
        "zorven-wf2-bsa-origin",
    ],
    "CAA": [
        "zorven-wf3-caa-system",
        "zorven-wf3-caa-blueprint",
        "zorven-wf3-caa-targeting",
    ],
    "CGA": [
        "zorven-wf3-cga-system",
        "zorven-wf3-cga-profiling",
        "zorven-wf3-cga-copywriting",
        "zorven-wf3-cga-compliance",
    ],
    "ADPUB": [
        "zorven-wf3-adpub-system",
        "zorven-wf3-adpub-publishing",
        "zorven-wf3-adpub-approval",
    ],
    "COA": [
        "zorven-wf3-coa-system",
        "zorven-wf3-coa-optimization",
        "zorven-wf3-coa-recommendation",
        "zorven-wf3-coa-planner",
    ],
    "ILA": [
        "zorven-wf3-ila-system",
        "zorven-wf3-ila-extraction",
        "zorven-wf3-ila-synthesis",
        "zorven-wf3-ila-planner",
    ],
}

# Per-agent minimum counts
AGENT_MINIMUMS: dict[str, int] = {
    "CGA": 20,
    "COA": 20,
    "BPA": 20,
    "BPV": 20,
    "CAA": 15,
    "ADPUB": 15,
    "ILA": 15,
    "MRA": 15,
    "CIA": 15,
    "APA": 15,
    "TCIA": 15,
    "VoCA": 15,
    "BAA": 15,
    "NTA": 15,
    "BSA": 15,
}

# ---------------------------------------------------------------------------
# Expected output templates per agent per prompt-type suffix
# ---------------------------------------------------------------------------

_EXPECTED_OUTPUTS: dict[str, dict[str, str]] = {
    "MRA": {
        "system": (
            "Initialize market research analysis for {brand} in {industry}, "
            "establishing TAM/SAM/SOM framework and research methodology."
        ),
        "planning": (
            "Research plan covering market sizing, growth trends, and "
            "competitive landscape for {brand} targeting {audience}."
        ),
        "synthesis": (
            "Synthesized market report with addressable market estimate, "
            "key growth drivers, and entry barriers for {industry}."
        ),
    },
    "CIA": {
        "system": (
            "Initialize competitor intelligence framework for {brand} "
            "with SWOT template and benchmarking criteria."
        ),
        "analysis": (
            "Detailed competitive analysis identifying top 5 rivals, "
            "their positioning, and {brand}'s differentiation gaps."
        ),
        "benchmarking": (
            "Benchmarking scorecard comparing {brand} against competitors "
            "on pricing, features, market share, and brand perception."
        ),
    },
    "APA": {
        "system": (
            "Initialize audience persona profiling for {brand} with "
            "demographic and psychographic segmentation framework."
        ),
        "profiling": (
            "Three detailed personas for {audience} including motivations, "
            "pain points, media habits, and purchase triggers."
        ),
        "segmentation": (
            "Audience segmentation matrix for {brand} with prioritized "
            "segments ranked by revenue potential and acquisition cost."
        ),
    },
    "TCIA": {
        "system": (
            "Initialize trend and cultural intelligence monitoring for "
            "{brand} in the {industry} sector."
        ),
        "monitoring": (
            "Trend radar identifying 8-10 macro and micro trends affecting "
            "{industry} with relevance scores for {brand}."
        ),
        "scoring": (
            "Opportunity scoring matrix rating each trend on impact, "
            "feasibility, and brand-fit for {brand}."
        ),
    },
    "VoCA": {
        "system": (
            "Initialize voice of customer analysis framework for {brand} "
            "with sentiment taxonomy and NPS methodology."
        ),
        "sentiment": (
            "Sentiment analysis across review channels showing {brand}'s "
            "NPS trajectory and key satisfaction drivers."
        ),
        "themes": (
            "Thematic clustering of customer feedback revealing top 5 "
            "praise themes and top 5 complaint themes for {brand}."
        ),
    },
    "BPA": {
        "system": (
            "Initialize brand positioning strategy for {brand} with "
            "differentiation framework and competitive context."
        ),
        "positioning": (
            "Positioning statement and value proposition for {brand} "
            "targeting {audience} with clear competitive differentiation."
        ),
        "perceptual": (
            "Perceptual map plotting {brand} and competitors on two key "
            "dimensions relevant to {industry} purchase decisions."
        ),
    },
    "BAA": {
        "system": (
            "Initialize brand architecture analysis for {brand} with "
            "hierarchy assessment and portfolio strategy framework."
        ),
        "hierarchy": (
            "Brand hierarchy tree for {brand} defining master brand, "
            "sub-brands, and endorsed brand relationships."
        ),
        "portfolio": (
            "Portfolio growth strategy for {brand} identifying extension "
            "opportunities and cannibalization risks."
        ),
    },
    "BPV": {
        "system": (
            "Initialize brand personality and values framework for {brand} "
            "using Aaker 5D model and archetype mapping."
        ),
        "personality": (
            "Aaker 5D personality profile for {brand} with primary archetype, "
            "trait scores, and alignment to {audience} expectations."
        ),
        "voice": (
            "Brand voice matrix for {brand} defining tone, vocabulary, "
            "grammar style, and channel-specific adaptations."
        ),
    },
    "NTA": {
        "system": (
            "Initialize naming and tagline development for {brand} with "
            "linguistic criteria and availability checking framework."
        ),
        "naming": (
            "Five name candidates for {brand}'s new product line with "
            "etymology, domain availability, and trademark risk assessment."
        ),
        "tagline": (
            "Three tagline options for {brand} balancing memorability, "
            "brand promise, and emotional resonance for {audience}."
        ),
    },
    "BSA": {
        "system": (
            "Initialize brand story and narrative framework for {brand} "
            "with origin story template and mission/vision structure."
        ),
        "narrative": (
            "Brand narrative arc for {brand} connecting founder motivation, "
            "customer transformation, and societal impact."
        ),
        "origin": (
            "Origin story for {brand} highlighting the founding insight, "
            "early struggles, and breakthrough moment that defines the brand."
        ),
    },
    "CAA": {
        "system": (
            "Initialize campaign architecture for {brand} with Meta Ads "
            "blueprint, funnel mapping, and budget allocation framework."
        ),
        "blueprint": (
            "Campaign blueprint for {brand} with three funnel stages, "
            "ad set structure, and budget split across awareness/consideration/conversion."
        ),
        "targeting": (
            "Audience targeting strategy for {brand}'s Meta campaign with "
            "custom audiences, lookalikes, and interest-based segments."
        ),
    },
    "CGA": {
        "system": (
            "Initialize creative generation pipeline for {brand} with "
            "visual style guide and copy framework."
        ),
        "profiling": (
            "Creative profiles for {brand}'s campaign: three visual concepts "
            "with mood boards, color palettes, and imagery direction."
        ),
        "copywriting": (
            "Ad copy variants for {brand}: primary text, headline, and "
            "description for each funnel stage targeting {audience}."
        ),
        "compliance": (
            "Meta Ads compliance review for {brand}'s creatives checking "
            "text-to-image ratio, prohibited content, and policy adherence."
        ),
    },
    "ADPUB": {
        "system": (
            "Initialize ad publishing workflow for {brand} with Meta Ads API "
            "configuration and human approval gate setup."
        ),
        "publishing": (
            "Publishing plan for {brand}'s campaign with ad set scheduling, "
            "bid strategy, and pixel event configuration."
        ),
        "approval": (
            "Approval checklist for {brand}'s ad creatives covering brand "
            "guidelines, legal review, and stakeholder sign-off status."
        ),
    },
    "COA": {
        "system": (
            "Initialize campaign optimization framework for {brand} with "
            "KPI thresholds, guardrails, and automated rule definitions."
        ),
        "optimization": (
            "Optimization recommendations for {brand}'s campaign: budget "
            "reallocation, audience refinement, and creative refresh triggers."
        ),
        "recommendation": (
            "Specific action recommendations for {brand}: pause underperformers, "
            "scale winners, and test new creative variants."
        ),
        "planner": (
            "Optimization schedule for {brand}'s campaign with daily check "
            "cadence, weekly review milestones, and escalation criteria."
        ),
    },
    "ILA": {
        "system": (
            "Initialize intelligence loop for {brand} consuming optimization "
            "learnings and extracting reusable campaign insights."
        ),
        "extraction": (
            "Extracted insights from {brand}'s campaign data: winning audience "
            "segments, top creative themes, and cost efficiency patterns."
        ),
        "synthesis": (
            "Synthesized learnings for {brand}: cross-campaign patterns, "
            "audience fatigue signals, and creative longevity benchmarks."
        ),
        "planner": (
            "Intelligence loop execution plan for {brand} defining insight "
            "extraction cadence, RAG ingestion schedule, and feedback routing."
        ),
    },
}

# ---------------------------------------------------------------------------
# Context builders per workflow
# ---------------------------------------------------------------------------


def _wf1_context(brand_info: dict[str, str]) -> dict[str, Any]:
    return {
        "context.brand_name": brand_info["brand_name"],
        "context.industry": brand_info["_industry"],
        "context.target_audience": brand_info["target_audience"],
        "context.brand_voice": brand_info["brand_voice"],
        "context.product_description": brand_info["product_description"],
        "context.query": f"Analyze market opportunity for {brand_info['brand_name']}",
        "context.competitors": f"Top 5 competitors in {brand_info['_industry']}",
        "context.audience_data": f"Demographics and behaviors of {brand_info['target_audience']}",
        "context.trends": f"Current macro and micro trends in {brand_info['_industry']}",
        "context.feedback_data": f"Customer reviews and NPS data for {brand_info['brand_name']}",
    }


def _wf2_context(brand_info: dict[str, str]) -> dict[str, Any]:
    return {
        "context.brand_name": brand_info["brand_name"],
        "context.industry": brand_info["_industry"],
        "context.target_audience": brand_info["target_audience"],
        "context.brand_voice": brand_info["brand_voice"],
        "context.product_description": brand_info["product_description"],
        "context.market_research": f"TAM/SAM/SOM analysis for {brand_info['_industry']}",
        "context.positioning": f"{brand_info['brand_name']} value proposition and differentiation",
        "context.personality": f"Brand archetype and Aaker 5D profile for {brand_info['brand_name']}",
        "context.voice": brand_info["brand_voice"],
        "context.architecture": f"Brand hierarchy for {brand_info['brand_name']}",
        "context.values": f"Core values driving {brand_info['brand_name']}'s mission",
        "context.founder_info": f"Founder story and motivation behind {brand_info['brand_name']}",
    }


def _wf3_context(brand_info: dict[str, str]) -> dict[str, Any]:
    return {
        "context.brand_name": brand_info["brand_name"],
        "context.industry": brand_info["_industry"],
        "context.target_audience": brand_info["target_audience"],
        "context.brand_voice": brand_info["brand_voice"],
        "context.product_description": brand_info["product_description"],
        "context.objective": f"Drive trial signups for {brand_info['brand_name']}",
        "context.budget": brand_info["budget_range"],
        "context.personas": f"Three prioritized personas for {brand_info['target_audience']}",
        "context.campaign_blueprint": f"3-stage funnel campaign for {brand_info['brand_name']}",
        "context.creative_profiles": f"Visual and copy profiles for {brand_info['brand_name']} ads",
        "context.campaign_metrics": f"CTR, CPA, ROAS benchmarks for {brand_info['_industry']}",
        "context.performance_data": f"Last 14 days performance for {brand_info['brand_name']} campaigns",
        "context.guardrails": "Max CPA $45, min ROAS 2.5x, daily budget cap adherence",
    }


_CONTEXT_BUILDERS = {
    "MRA": _wf1_context,
    "CIA": _wf1_context,
    "APA": _wf1_context,
    "TCIA": _wf1_context,
    "VoCA": _wf1_context,
    "BPA": _wf2_context,
    "BAA": _wf2_context,
    "BPV": _wf2_context,
    "NTA": _wf2_context,
    "BSA": _wf2_context,
    "CAA": _wf3_context,
    "CGA": _wf3_context,
    "ADPUB": _wf3_context,
    "COA": _wf3_context,
    "ILA": _wf3_context,
}

# ---------------------------------------------------------------------------
# Source distribution logic
# ---------------------------------------------------------------------------

# Source assignment by (industry_index * 3 + maturity_index) mod pattern
_SOURCE_CYCLE = (
    ["manual"] * 12 + ["synthetic"] * 5 + ["mined"] * 2 + ["adversarial"] * 1
)  # 60%/25%/10%/5%


def _pick_source(idx: int) -> str:
    return _SOURCE_CYCLE[idx % len(_SOURCE_CYCLE)]


# ---------------------------------------------------------------------------
# Objective pool (varies by industry to keep examples diverse)
# ---------------------------------------------------------------------------

_OBJECTIVES = [
    "brand awareness launch",
    "lead generation acceleration",
    "market share expansion",
    "customer retention improvement",
    "product-market fit validation",
    "premium positioning pivot",
    "geographic expansion",
    "audience segment penetration",
    "competitive displacement",
    "brand refresh and repositioning",
    "seasonal campaign optimization",
    "thought leadership establishment",
]

_AUDIENCE_COMPLEXITIES = [
    "single-segment",
    "multi-segment",
    "niche-focused",
    "mass-market",
]

_VOICE_TONES = [
    "authoritative",
    "playful",
    "empathetic",
    "provocative",
    "minimalist",
    "inspirational",
]

# ---------------------------------------------------------------------------
# Helper function
# ---------------------------------------------------------------------------


def _make_example(
    prompt_name: str,
    agent_code: str,
    industry: str,
    maturity: str,
    source: str,
    objective: str,
    voice_tone: str,
    audience_complexity: str,
) -> GoldenExample:
    """Build a single GoldenExample with context and expected output."""
    brand_info = {**_BRANDS[industry], "_industry": industry}
    brand = brand_info["brand_name"]
    audience = brand_info["target_audience"]

    # Build context from workflow
    context_builder = _CONTEXT_BUILDERS[agent_code]
    input_context = context_builder(brand_info)

    # Determine prompt type suffix (last segment after last hyphen)
    suffix = prompt_name.rsplit("-", 1)[-1]
    template = _EXPECTED_OUTPUTS[agent_code][suffix]
    expected_output = template.format(
        brand=brand,
        industry=industry,
        audience=audience,
    )

    return GoldenExample(
        prompt_name=prompt_name,
        agent_code=agent_code,
        input_context=input_context,
        expected_output=expected_output,
        source=source,
        metadata_extra={
            "industry": industry,
            "brand_maturity": maturity,
            "objective": objective,
            "voice_tone": voice_tone,
            "budget_range": brand_info["budget_range"],
            "audience_complexity": audience_complexity,
        },
    )


# ---------------------------------------------------------------------------
# Generate examples via systematic loops
# ---------------------------------------------------------------------------


def _generate_all_examples() -> list[GoldenExample]:
    """
    Generate ~260 golden examples across all 15 agents.

    Strategy:
    - For agents needing >= 20 (CGA, COA, BPA, BPV): use all 12 industries
      with rotating maturities and extra prompt coverage.
    - For agents needing >= 15: use 12 industries + 3 extras with varied
      maturity to reach 15.
    - Adversarial examples are added separately at the end.
    """
    examples: list[GoldenExample] = []
    global_idx = 0

    for agent_code, prompts in AGENT_PROMPTS.items():
        minimum = AGENT_MINIMUMS[agent_code]
        agent_examples: list[GoldenExample] = []
        num_prompts = len(prompts)

        # Phase 1: One example per industry per prompt (round-robin)
        for ind_idx, industry in enumerate(INDUSTRIES):
            prompt_name = prompts[ind_idx % num_prompts]
            mat_idx = ind_idx % len(MATURITIES)
            maturity = MATURITIES[mat_idx]
            source = _pick_source(global_idx)
            objective = _OBJECTIVES[ind_idx % len(_OBJECTIVES)]
            voice_tone = _VOICE_TONES[ind_idx % len(_VOICE_TONES)]
            audience_cx = _AUDIENCE_COMPLEXITIES[ind_idx % len(_AUDIENCE_COMPLEXITIES)]

            agent_examples.append(
                _make_example(
                    prompt_name=prompt_name,
                    agent_code=agent_code,
                    industry=industry,
                    maturity=maturity,
                    source=source,
                    objective=objective,
                    voice_tone=voice_tone,
                    audience_complexity=audience_cx,
                )
            )
            global_idx += 1

        # Phase 2: Fill remaining slots to reach minimum
        remaining = minimum - len(agent_examples)
        fill_idx = 0
        while remaining > 0:
            industry = INDUSTRIES[fill_idx % len(INDUSTRIES)]
            # Use a different prompt than phase 1 for this industry
            prompt_name = prompts[(fill_idx + 1) % num_prompts]
            maturity = MATURITIES[(fill_idx + 1) % len(MATURITIES)]
            source = _pick_source(global_idx)
            objective = _OBJECTIVES[(fill_idx + 3) % len(_OBJECTIVES)]
            voice_tone = _VOICE_TONES[(fill_idx + 2) % len(_VOICE_TONES)]
            audience_cx = _AUDIENCE_COMPLEXITIES[
                (fill_idx + 1) % len(_AUDIENCE_COMPLEXITIES)
            ]

            agent_examples.append(
                _make_example(
                    prompt_name=prompt_name,
                    agent_code=agent_code,
                    industry=industry,
                    maturity=maturity,
                    source=source,
                    objective=objective,
                    voice_tone=voice_tone,
                    audience_complexity=audience_cx,
                )
            )
            global_idx += 1
            fill_idx += 1
            remaining -= 1

        examples.extend(agent_examples)

    # Phase 3: Adversarial examples (edge cases, ~5% of total = ~13 examples)
    adversarial_cases = _generate_adversarial_examples()
    examples.extend(adversarial_cases)

    return examples


def _generate_adversarial_examples() -> list[GoldenExample]:
    """
    Targeted adversarial examples testing edge cases:
    - Empty/minimal context
    - Conflicting brand signals
    - Extreme budget constraints
    - Unusual industry combinations
    - Multi-language audience
    """
    adversarial: list[GoldenExample] = []

    # 1. CGA: Minimal context — brand name only
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf3-cga-copywriting",
            agent_code="CGA",
            input_context={
                "context.brand_name": "UnknownBrand",
                "context.industry": "",
                "context.target_audience": "",
                "context.brand_voice": "",
                "context.product_description": "",
                "context.objective": "Generate ad copy",
                "context.budget": "",
                "context.personas": "",
                "context.campaign_blueprint": "",
                "context.creative_profiles": "",
                "context.campaign_metrics": "",
                "context.performance_data": "",
                "context.guardrails": "",
            },
            expected_output=(
                "Request clarification on missing brand context before "
                "generating copy; produce placeholder variants with caveats."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Unknown",
                "brand_maturity": "new",
                "objective": "incomplete context handling",
                "voice_tone": "neutral",
                "budget_range": "unspecified",
                "audience_complexity": "unknown",
            },
        )
    )

    # 2. COA: Conflicting performance signals
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf3-coa-optimization",
            agent_code="COA",
            input_context={
                "context.brand_name": "ParadoxCo",
                "context.industry": "Financial Services",
                "context.target_audience": "High-net-worth individuals and college students",
                "context.brand_voice": "Both ultra-formal and slang-heavy",
                "context.product_description": "Premium investment app that is also free",
                "context.objective": "Maximize ROAS while minimizing spend to zero",
                "context.budget": "$0",
                "context.personas": "Contradictory: luxury seekers who refuse to pay",
                "context.campaign_blueprint": "Full funnel with no budget allocation",
                "context.creative_profiles": "Minimalist maximalism aesthetic",
                "context.campaign_metrics": "CTR 15% but conversion 0.01%",
                "context.performance_data": "High engagement, zero revenue",
                "context.guardrails": "No spend allowed, must generate revenue",
            },
            expected_output=(
                "Flag contradictory objectives and recommend resolving budget "
                "and audience conflicts before optimization can proceed."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Financial Services",
                "brand_maturity": "new",
                "objective": "conflicting signals detection",
                "voice_tone": "conflicting",
                "budget_range": "$0",
                "audience_complexity": "contradictory",
            },
        )
    )

    # 3. BPA: Extremely crowded market positioning
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf2-bpa-positioning",
            agent_code="BPA",
            input_context={
                "context.brand_name": "YetAnotherCRM",
                "context.industry": "SaaS/Technology",
                "context.target_audience": "SMB sales teams already using 3+ CRMs",
                "context.brand_voice": "Generic corporate",
                "context.product_description": "CRM platform with standard features",
                "context.market_research": "Market saturated with 200+ CRM vendors",
                "context.positioning": "No clear differentiator identified",
                "context.personality": "Undefined",
                "context.voice": "Generic corporate",
                "context.architecture": "Single product",
                "context.values": "Efficiency",
                "context.founder_info": "Former Salesforce employee",
            },
            expected_output=(
                "Identify micro-niche positioning opportunities in the "
                "saturated CRM market; recommend vertical specialization."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "SaaS/Technology",
                "brand_maturity": "new",
                "objective": "saturated market positioning",
                "voice_tone": "generic",
                "budget_range": "$10K-30K/quarter",
                "audience_complexity": "over-served",
            },
        )
    )

    # 4. BPV: Cross-cultural brand personality tension
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf2-bpv-personality",
            agent_code="BPV",
            input_context={
                "context.brand_name": "GlobalHarmony",
                "context.industry": "Entertainment/Media",
                "context.target_audience": "Gen-Z audiences across US, Japan, Saudi Arabia, and Brazil",
                "context.brand_voice": "Must resonate across vastly different cultural norms",
                "context.product_description": "Global streaming platform for independent creators",
                "context.market_research": "Cultural sensitivity requirements vary dramatically",
                "context.positioning": "Inclusive global platform",
                "context.personality": "Must avoid cultural offense while being authentic",
                "context.voice": "Adaptable across cultures",
                "context.architecture": "Single global brand",
                "context.values": "Diversity, creativity, authenticity",
                "context.founder_info": "Multi-national founding team from 4 countries",
            },
            expected_output=(
                "Define a universal personality core with culture-specific "
                "expression guidelines for each target market."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Entertainment/Media",
                "brand_maturity": "new",
                "objective": "cross-cultural consistency",
                "voice_tone": "culturally adaptive",
                "budget_range": "$200K-500K/quarter",
                "audience_complexity": "multi-cultural",
            },
        )
    )

    # 5. ILA: Noisy data extraction
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf3-ila-extraction",
            agent_code="ILA",
            input_context={
                "context.brand_name": "NoisyCo",
                "context.industry": "E-commerce/Retail",
                "context.target_audience": "Bargain hunters",
                "context.brand_voice": "Aggressive discounting",
                "context.product_description": "Flash sale platform",
                "context.objective": "Extract learnings from chaotic campaign data",
                "context.budget": "$5K/quarter",
                "context.personas": "Price-sensitive impulse buyers",
                "context.campaign_blueprint": "Ad-hoc campaigns with no structure",
                "context.creative_profiles": "Inconsistent branding across 50+ creatives",
                "context.campaign_metrics": "Metrics contradict across platforms",
                "context.performance_data": "Incomplete tracking, missing attribution",
                "context.guardrails": "None defined",
            },
            expected_output=(
                "Identify data quality issues, recommend tracking fixes, and "
                "extract limited reliable insights from available clean data."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "E-commerce/Retail",
                "brand_maturity": "emerging",
                "objective": "noisy data handling",
                "voice_tone": "aggressive",
                "budget_range": "$5K/quarter",
                "audience_complexity": "single-segment",
            },
        )
    )

    # 6. CAA: Micro-budget campaign architecture
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf3-caa-blueprint",
            agent_code="CAA",
            input_context={
                "context.brand_name": "TinyStartup",
                "context.industry": "Education/EdTech",
                "context.target_audience": "Parents of K-3 students in rural areas",
                "context.brand_voice": "Friendly and accessible",
                "context.product_description": "Free reading app for early learners",
                "context.objective": "Drive app downloads on $500 total budget",
                "context.budget": "$500 total",
                "context.personas": "Budget-constrained parents with limited internet",
                "context.campaign_blueprint": "Single campaign with micro-budget",
                "context.creative_profiles": "DIY creative assets",
                "context.campaign_metrics": "Industry avg CPI $3.50",
                "context.performance_data": "No historical data",
                "context.guardrails": "Cannot exceed $500 total spend",
            },
            expected_output=(
                "Design micro-budget campaign focusing on single best-performing "
                "channel with organic amplification strategy."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Education/EdTech",
                "brand_maturity": "new",
                "objective": "micro-budget optimization",
                "voice_tone": "friendly",
                "budget_range": "$500 total",
                "audience_complexity": "niche-focused",
            },
        )
    )

    # 7. ADPUB: Regulatory-heavy publishing
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf3-adpub-approval",
            agent_code="ADPUB",
            input_context={
                "context.brand_name": "MedClaim",
                "context.industry": "Healthcare/Wellness",
                "context.target_audience": "Patients with chronic conditions",
                "context.brand_voice": "Clinical and reassuring",
                "context.product_description": "FDA-pending supplement claiming health benefits",
                "context.objective": "Publish compliant health ads",
                "context.budget": "$50K/quarter",
                "context.personas": "Vulnerable health-seeking consumers",
                "context.campaign_blueprint": "Health claims campaign",
                "context.creative_profiles": "Before/after imagery with testimonials",
                "context.campaign_metrics": "N/A - first campaign",
                "context.performance_data": "No historical data",
                "context.guardrails": "FDA, FTC, Meta health ads policy compliance required",
            },
            expected_output=(
                "Flag potential health claim violations, require legal review "
                "before approval, and recommend compliant copy alternatives."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Healthcare/Wellness",
                "brand_maturity": "new",
                "objective": "regulatory compliance",
                "voice_tone": "clinical",
                "budget_range": "$50K/quarter",
                "audience_complexity": "vulnerable-population",
            },
        )
    )

    # 8. NTA: Trademark collision risk
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf2-nta-naming",
            agent_code="NTA",
            input_context={
                "context.brand_name": "Appel",
                "context.industry": "SaaS/Technology",
                "context.target_audience": "Enterprise developers",
                "context.brand_voice": "Innovative and bold",
                "context.product_description": "Developer productivity platform",
                "context.market_research": "Strong incumbents with protected trademarks",
                "context.positioning": "Premium developer experience",
                "context.personality": "Rebellious innovator",
                "context.voice": "Bold, technical",
                "context.architecture": "Single product brand",
                "context.values": "Developer freedom",
                "context.founder_info": "Two ex-FAANG engineers",
            },
            expected_output=(
                "Flag high trademark collision risk with Apple Inc., recommend "
                "alternative names with clear linguistic differentiation."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "SaaS/Technology",
                "brand_maturity": "new",
                "objective": "trademark risk detection",
                "voice_tone": "bold",
                "budget_range": "$30K-80K/quarter",
                "audience_complexity": "single-segment",
            },
        )
    )

    # 9. BSA: Founder controversy in origin story
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf2-bsa-origin",
            agent_code="BSA",
            input_context={
                "context.brand_name": "RedeemTech",
                "context.industry": "Professional Services",
                "context.target_audience": "SMB owners seeking consulting",
                "context.brand_voice": "Humble and transparent",
                "context.product_description": "Business turnaround consulting",
                "context.market_research": "Growing demand for turnaround services",
                "context.positioning": "Second-chance business partner",
                "context.personality": "Resilient and honest",
                "context.voice": "Humble, transparent",
                "context.architecture": "Single brand",
                "context.values": "Redemption, integrity, perseverance",
                "context.founder_info": "Founder previously led a company into bankruptcy",
            },
            expected_output=(
                "Frame the founder's past failure as a credibility asset for "
                "turnaround consulting while acknowledging lessons learned."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Professional Services",
                "brand_maturity": "new",
                "objective": "controversial founder narrative",
                "voice_tone": "humble",
                "budget_range": "$20K-50K/quarter",
                "audience_complexity": "trust-sensitive",
            },
        )
    )

    # 10. MRA: Emerging market with no data
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf1-mra-synthesis",
            agent_code="MRA",
            input_context={
                "context.brand_name": "QuantumLeap",
                "context.industry": "SaaS/Technology",
                "context.target_audience": "Quantum computing researchers",
                "context.brand_voice": "Pioneering and academic",
                "context.product_description": "Quantum algorithm marketplace",
                "context.query": "Size the quantum computing SaaS market",
                "context.competitors": "No direct competitors exist yet",
                "context.audience_data": "Fewer than 5,000 potential users globally",
                "context.trends": "Pre-commercial technology, 5-10 year horizon",
                "context.feedback_data": "No customer feedback available",
            },
            expected_output=(
                "Acknowledge data scarcity, use analogous market proxies for "
                "sizing, and provide wide confidence intervals on estimates."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "SaaS/Technology",
                "brand_maturity": "new",
                "objective": "data-scarce market sizing",
                "voice_tone": "academic",
                "budget_range": "$10K-40K/quarter",
                "audience_complexity": "ultra-niche",
            },
        )
    )

    # 11. VoCA: Astroturfed reviews
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf1-voca-sentiment",
            agent_code="VoCA",
            input_context={
                "context.brand_name": "ShadySupps",
                "context.industry": "Food & Beverage",
                "context.target_audience": "Fitness enthusiasts",
                "context.brand_voice": "Hype-driven",
                "context.product_description": "Pre-workout supplement",
                "context.query": "Analyze customer sentiment",
                "context.competitors": "Established supplement brands",
                "context.audience_data": "Young male fitness enthusiasts 18-30",
                "context.trends": "Clean label movement",
                "context.feedback_data": "95% 5-star reviews with identical phrasing patterns",
            },
            expected_output=(
                "Flag suspected astroturfing in review data, discount fake "
                "reviews from sentiment score, and report authentic signal."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Food & Beverage",
                "brand_maturity": "emerging",
                "objective": "fake review detection",
                "voice_tone": "hype-driven",
                "budget_range": "$10K-30K/quarter",
                "audience_complexity": "single-segment",
            },
        )
    )

    # 12. BAA: Portfolio cannibalization
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf2-baa-portfolio",
            agent_code="BAA",
            input_context={
                "context.brand_name": "OmniSoft",
                "context.industry": "SaaS/Technology",
                "context.target_audience": "Enterprise IT teams",
                "context.brand_voice": "Enterprise-grade authoritative",
                "context.product_description": "Suite of 12 overlapping SaaS products",
                "context.market_research": "Customers confused by product overlap",
                "context.positioning": "End-to-end enterprise platform",
                "context.personality": "Reliable but complex",
                "context.voice": "Technical and comprehensive",
                "context.architecture": "12 sub-brands with overlapping features",
                "context.values": "Completeness, integration",
                "context.founder_info": "Growth-through-acquisition strategy",
            },
            expected_output=(
                "Map product overlap, recommend consolidation of 12 brands "
                "into 4-5 clear categories, and define migration path."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "SaaS/Technology",
                "brand_maturity": "established",
                "objective": "portfolio rationalization",
                "voice_tone": "authoritative",
                "budget_range": "$100K-300K/quarter",
                "audience_complexity": "enterprise-complex",
            },
        )
    )

    # 13. APA: Privacy-constrained profiling
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf1-apa-profiling",
            agent_code="APA",
            input_context={
                "context.brand_name": "KinderSafe",
                "context.industry": "Education/EdTech",
                "context.target_audience": "Children aged 6-12 and their parents",
                "context.brand_voice": "Safe, nurturing, COPPA-compliant",
                "context.product_description": "Educational gaming platform for children",
                "context.query": "Profile our target audience",
                "context.competitors": "PBS Kids, Khan Academy Kids",
                "context.audience_data": "Cannot collect data from children under 13",
                "context.trends": "COPPA enforcement increasing, EU DSA compliance",
                "context.feedback_data": "Parent reviews only, no child data",
            },
            expected_output=(
                "Build parent-proxy personas respecting COPPA constraints; "
                "profile children's needs through parent behavioral data."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Education/EdTech",
                "brand_maturity": "emerging",
                "objective": "privacy-constrained profiling",
                "voice_tone": "nurturing",
                "budget_range": "$15K-50K/quarter",
                "audience_complexity": "regulated-minors",
            },
        )
    )

    # 14. TCIA: Trend fatigue in oversaturated category
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf1-tcia-scoring",
            agent_code="TCIA",
            input_context={
                "context.brand_name": "GenericAI",
                "context.industry": "SaaS/Technology",
                "context.target_audience": "Enterprise buyers fatigued by AI hype",
                "context.brand_voice": "Measured and substantive",
                "context.product_description": "Yet another AI assistant tool",
                "context.query": "Score trend opportunities in AI tools market",
                "context.competitors": "ChatGPT, Gemini, Copilot, and 500+ startups",
                "context.audience_data": "Buyers reporting AI fatigue and skepticism",
                "context.trends": "AI hype cycle entering trough of disillusionment",
                "context.feedback_data": "Prospects say 'we already have too many AI tools'",
            },
            expected_output=(
                "Score AI trends with deflated opportunity ratings reflecting "
                "market saturation; recommend differentiation via outcomes."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "SaaS/Technology",
                "brand_maturity": "new",
                "objective": "hype-cycle navigation",
                "voice_tone": "measured",
                "budget_range": "$20K-60K/quarter",
                "audience_complexity": "skeptical-buyers",
            },
        )
    )

    # 15. CIA: Competitor with no public information
    adversarial.append(
        GoldenExample(
            prompt_name="zorven-wf1-cia-analysis",
            agent_code="CIA",
            input_context={
                "context.brand_name": "OpenLedger",
                "context.industry": "Financial Services",
                "context.target_audience": "Crypto-native DeFi users",
                "context.brand_voice": "Transparent and technical",
                "context.product_description": "Decentralized lending protocol",
                "context.query": "Analyze stealth-mode competitors",
                "context.competitors": "Three pre-launch stealth competitors with no public data",
                "context.audience_data": "Crypto community on Discord and Twitter",
                "context.trends": "DeFi regulatory uncertainty increasing",
                "context.feedback_data": "Community speculation only, no verified data",
            },
            expected_output=(
                "Acknowledge intelligence gaps for stealth competitors, use "
                "proxy signals from hiring patterns and funding rounds."
            ),
            source="adversarial",
            metadata_extra={
                "industry": "Financial Services",
                "brand_maturity": "new",
                "objective": "stealth competitor analysis",
                "voice_tone": "technical",
                "budget_range": "$15K-40K/quarter",
                "audience_complexity": "crypto-native",
            },
        )
    )

    return adversarial


# ---------------------------------------------------------------------------
# Module-level dataset
# ---------------------------------------------------------------------------

GOLDEN_EXAMPLES: list[GoldenExample] = _generate_all_examples()


def get_examples_by_agent(agent_code: str) -> list[GoldenExample]:
    """Filter golden examples by agent code."""
    return [ex for ex in GOLDEN_EXAMPLES if ex.agent_code == agent_code]


def get_examples_by_source(source: str) -> list[GoldenExample]:
    """Filter golden examples by source type."""
    return [ex for ex in GOLDEN_EXAMPLES if ex.source == source]


def get_examples_by_industry(industry: str) -> list[GoldenExample]:
    """Filter golden examples by industry vertical."""
    return [
        ex for ex in GOLDEN_EXAMPLES if ex.metadata_extra.get("industry") == industry
    ]


def validate_golden_dataset() -> dict[str, Any]:
    """
    Validate the golden dataset meets all requirements.
    Returns a summary dict with counts and any violations.
    """
    total = len(GOLDEN_EXAMPLES)
    by_agent: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_industry: dict[str, int] = {}
    violations: list[str] = []

    for ex in GOLDEN_EXAMPLES:
        by_agent[ex.agent_code] = by_agent.get(ex.agent_code, 0) + 1
        by_source[ex.source] = by_source.get(ex.source, 0) + 1
        industry = ex.metadata_extra.get("industry", "Unknown")
        by_industry[industry] = by_industry.get(industry, 0) + 1

        # Validate context keys start with "context."
        for key in ex.input_context:
            if not key.startswith("context."):
                violations.append(
                    f"{ex.prompt_name}: key '{key}' missing 'context.' prefix"
                )

        # Validate metadata_extra has required fields
        required_meta = {
            "industry",
            "brand_maturity",
            "objective",
            "voice_tone",
            "budget_range",
            "audience_complexity",
        }
        missing = required_meta - set(ex.metadata_extra.keys())
        if missing:
            violations.append(f"{ex.prompt_name}: missing metadata fields {missing}")

    # Check per-agent minimums
    for agent_code, minimum in AGENT_MINIMUMS.items():
        actual = by_agent.get(agent_code, 0)
        if actual < minimum:
            violations.append(
                f"{agent_code}: has {actual} examples, needs >= {minimum}"
            )

    return {
        "total": total,
        "by_agent": by_agent,
        "by_source": by_source,
        "by_industry": by_industry,
        "violations": violations,
    }
