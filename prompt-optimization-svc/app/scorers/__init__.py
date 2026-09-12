"""Scorer library for GEPA prompt optimization (§5.1, §5.2)."""

from app.scorers.ila import (
    ILA_SCORERS,
    learning_depth,
    meta_policy,
)
from app.scorers.wf1 import (
    WF1_SCORERS,
    competitor_accuracy,
    market_completeness,
    persona_quality,
    trend_relevance,
    voca_sentiment,
)
from app.scorers.wf2 import (
    WF2_SCORERS,
    architecture_coherence,
    name_quality,
    narrative_engagement,
    positioning_clarity,
    voice_consistency,
)
from app.scorers.coa import (
    COA_SCORERS,
    data_grounding,
    guardrail_compliance,
    prioritization_quality,
    recommendation_actionability,
)
from app.scorers.caa import (
    CAA_SCORERS,
    budget_rationality,
    funnel_coverage,
    structure_validity,
    targeting_quality,
)
from app.scorers.cga import (
    CGA_SCORERS,
    brand_voice_match,
    character_limits,
    creative_compliance,
    cta_effectiveness,
    variant_diversity,
)
from app.scorers.oia import (
    OIA_SCORERS,
    extraction_accuracy,
    followup_usefulness,
    media_analysis_accuracy,
    questionnaire_coverage,
    research_factuality,
    stream_attachment,
    sufficiency_agreement,
    summary_faithfulness,
)
from app.scorers.common import (
    brand_voice,
    json_compliance,
    pii_safety,
    token_efficiency,
)

COMMON_SCORERS = [json_compliance, pii_safety, token_efficiency, brand_voice]

__all__ = [
    "COMMON_SCORERS",
    "CGA_SCORERS",
    "CAA_SCORERS",
    "COA_SCORERS",
    "OIA_SCORERS",
    "WF1_SCORERS",
    "WF2_SCORERS",
    "ILA_SCORERS",
    "json_compliance",
    "pii_safety",
    "token_efficiency",
    "brand_voice",
    "creative_compliance",
    "character_limits",
    "variant_diversity",
    "brand_voice_match",
    "cta_effectiveness",
    "structure_validity",
    "budget_rationality",
    "funnel_coverage",
    "targeting_quality",
    "recommendation_actionability",
    "guardrail_compliance",
    "data_grounding",
    "prioritization_quality",
    "market_completeness",
    "competitor_accuracy",
    "persona_quality",
    "trend_relevance",
    "voca_sentiment",
    "positioning_clarity",
    "architecture_coherence",
    "voice_consistency",
    "name_quality",
    "narrative_engagement",
    "learning_depth",
    "meta_policy",
    "research_factuality",
    "questionnaire_coverage",
    "stream_attachment",
    "sufficiency_agreement",
    "followup_usefulness",
    "media_analysis_accuracy",
    "summary_faithfulness",
    "extraction_accuracy",
]
