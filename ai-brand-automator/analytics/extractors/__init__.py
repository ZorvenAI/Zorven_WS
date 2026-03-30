from analytics.extractors.brand_discovery import BrandDiscoveryExtractor
from analytics.extractors.brand_equity import BrandEquityExtractor
from analytics.extractors.brand_analysis import BrandAnalysisExtractor
from analytics.extractors.brand_architecture import BrandArchitectureExtractor
from analytics.extractors.brand_naming import BrandNamingExtractor
from analytics.extractors.brand_personality import BrandPersonalityExtractor
from analytics.extractors.brand_positioning import BrandPositioningExtractor
from analytics.extractors.content_social import ContentSocialExtractor

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
