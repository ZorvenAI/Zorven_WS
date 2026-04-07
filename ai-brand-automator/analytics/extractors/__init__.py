from analytics.extractors.brand_discovery import BrandDiscoveryExtractor
from analytics.extractors.brand_equity import BrandEquityExtractor
from analytics.extractors.brand_analysis import BrandAnalysisExtractor
from analytics.extractors.brand_architecture import BrandArchitectureExtractor
from analytics.extractors.brand_naming import BrandNamingExtractor
from analytics.extractors.brand_personality import BrandPersonalityExtractor
from analytics.extractors.brand_positioning import BrandPositioningExtractor
from analytics.extractors.brand_story import BrandStoryExtractor
from analytics.extractors.campaign_architecture import CampaignArchitectureExtractor
from analytics.extractors.content_social import ContentSocialExtractor
from analytics.extractors.creative_generation import CreativeGenerationExtractor
from analytics.extractors.ad_publishing import AdPublishingExtractor
from analytics.extractors.continuous_optimization import (
    ContinuousOptimizationExtractor,
)
from analytics.extractors.intelligence_loop import IntelligenceLoopExtractor

# Pipeline ID → Extractor mapping
# Covers all pipeline IDs from seed_manifests.py
PIPELINE_EXTRACTORS = {
    # Brand discovery pipelines (all 5 agents)
    "brand-discovery-complete": BrandDiscoveryExtractor(),
    "brand-discovery-full": BrandDiscoveryExtractor(),
    # Brand equity / valuation
    "iso-brand-equity": BrandEquityExtractor(),
    # Brand analysis / competitor audit
    "brand-analysis": BrandAnalysisExtractor(),
    "competitor-audit": BrandAnalysisExtractor(),
    # Individual agent pipelines (extract what they produce)
    "voice-of-customer": BrandDiscoveryExtractor(),
    "audience-persona": BrandDiscoveryExtractor(),
    "audience-persona-discovery": BrandDiscoveryExtractor(),
    "trend-cultural-insights": BrandDiscoveryExtractor(),
    "competitor-intelligence": BrandAnalysisExtractor(),
    "market-research": BrandDiscoveryExtractor(),
    "market-research-competitor-intel": BrandAnalysisExtractor(),
    "market-research-report": BrandDiscoveryExtractor(),
    # Content / social pipelines
    "blog-authoring": ContentSocialExtractor(),
    "content-social-publish": ContentSocialExtractor(),
    "social-promotion": ContentSocialExtractor(),
    "social-post": ContentSocialExtractor(),
    "rag-blog-social": ContentSocialExtractor(),
    "rag-blog-authoring": ContentSocialExtractor(),
    "content-strategy": ContentSocialExtractor(),
    "default-full-pipeline": ContentSocialExtractor(),
    # Brand positioning (WF2)
    "brand-strategy-positioning": BrandPositioningExtractor(),
    # Brand architecture (WF2)
    "brand-strategy-architecture": BrandArchitectureExtractor(),
    # Brand personality (WF2)
    "brand-strategy-personality": BrandPersonalityExtractor(),
    # Brand naming & tagline (WF2)
    "brand-strategy-naming": BrandNamingExtractor(),
    # Brand story & narrative (WF2)
    "brand-strategy-story": BrandStoryExtractor(),
    # Campaign architecture (WF3)
    "meta-campaign-architecture": CampaignArchitectureExtractor(),
    # Creative generation (WF3)
    "meta-creative-generation": CreativeGenerationExtractor(),
    # Ad publishing (WF3)
    "meta-ad-publishing": AdPublishingExtractor(),
    "meta-ads-full": AdPublishingExtractor(),
    # Intelligence Loop (WF3.5)
    "meta-campaign-intelligence": IntelligenceLoopExtractor(),
    # General chat — uses brand discovery extractor to grab any
    # agent results that were composed dynamically
    "general-chat": BrandDiscoveryExtractor(),
}


def detect_extractor_from_result(result_data: dict):
    """Detect the best extractor based on result_data content.

    Used as fallback when pipeline_id is unknown (chat-mode Tier 1).
    """
    if not result_data:
        return None

    node_results = result_data.get("node_results", {})

    # Check for intelligence loop outputs (ILA-3.5) — must run before COA
    # since ILA is downstream of COA and may share some keys.
    has_ila = bool(
        node_results.get("campaign_intelligence")
        or result_data.get("intelligence_report")
        or result_data.get("scored_learnings")
    )
    if has_ila:
        return IntelligenceLoopExtractor()

    # Check for continuous optimization outputs (COA-3.4)
    has_coa = bool(
        node_results.get("continuous_optimization")
        or result_data.get("continuous_optimization")
        or result_data.get("optimization_tick_id")
    )

    if has_coa:
        return ContinuousOptimizationExtractor()

    # Check for ad publishing outputs (WF3, downstream of CGA)
    has_apa = bool(
        node_results.get("ad_publishing")
        or result_data.get("published_campaign")
        or result_data.get("approval_request_id")
    )

    if has_apa:
        return AdPublishingExtractor()

    # Check for creative generation outputs (WF3, downstream of CAA)
    has_cga = bool(
        node_results.get("creative_generation")
        or result_data.get("creative_package")
        or result_data.get("ad_units")
        or result_data.get("generated_images")
    )

    if has_cga:
        return CreativeGenerationExtractor()

    # Check for campaign architecture outputs (WF3)
    has_caa = bool(
        node_results.get("campaign_architecture")
        or result_data.get("blueprint")
        or result_data.get("funnel_map")
        or result_data.get("targeting_specs")
    )

    if has_caa:
        return CampaignArchitectureExtractor()

    # Check for brand story outputs (WF2) — check before NTA since BSA is capstone
    has_bsa = bool(
        node_results.get("brand_story")
        or result_data.get("origin_story")
        or result_data.get("narrative_package")
    )

    if has_bsa:
        return BrandStoryExtractor()

    # Check for brand naming outputs (WF2)
    has_nta = bool(
        node_results.get("brand_naming")
        or result_data.get("name_candidates")
        or result_data.get("naming_brief")
    )

    if has_nta:
        return BrandNamingExtractor()

    # Check for brand personality outputs (WF2)
    has_bpv = bool(
        node_results.get("brand_personality")
        or result_data.get("aaker_profile", {}).get("dimensions")
        or result_data.get("archetype", {}).get("primary")
    )

    if has_bpv:
        return BrandPersonalityExtractor()

    # Check for brand architecture outputs (WF2)
    has_baa = bool(
        node_results.get("brand_architecture")
        or result_data.get("hierarchy")
        or result_data.get("recommendation", {}).get("recommended_model")
    )

    if has_baa:
        return BrandArchitectureExtractor()

    # Check for brand positioning outputs (WF2)
    has_bpa = bool(
        node_results.get("brand_positioning")
        or result_data.get("recommended_positioning")
        or result_data.get("positioning_candidates")
    )

    if has_bpa:
        return BrandPositioningExtractor()

    # Check for discovery agent outputs
    has_voc = bool(
        node_results.get("voice_of_customer") or result_data.get("voc_health_score")
    )
    has_cia = bool(
        node_results.get("competitor_intelligence")
        or result_data.get("competitors_analyzed")
    )
    has_apa = bool(node_results.get("audience_persona") or result_data.get("personas"))
    has_tcia = bool(
        node_results.get("trend_cultural") or result_data.get("scored_trends")
    )

    if has_voc or has_cia or has_apa or has_tcia:
        return BrandDiscoveryExtractor()

    # Check for content/social outputs
    has_blog = bool(node_results.get("blog_author") or result_data.get("blog_content"))
    has_social = bool(
        node_results.get("social_promoter") or result_data.get("platforms_posted")
    )

    if has_blog or has_social:
        return ContentSocialExtractor()

    # Check for brand equity outputs
    if result_data.get("brand_equity") or result_data.get("valuation"):
        return BrandEquityExtractor()

    return None
